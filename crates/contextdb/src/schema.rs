use anyhow::{Result, anyhow, bail};

#[derive(Debug, Clone)]
pub struct Schema {
    pub models: Vec<Model>,
}

#[derive(Debug, Clone)]
pub struct Model {
    pub name: String,
    pub fields: Vec<Field>,
    pub indexes: Vec<Index>,
}

#[derive(Debug, Clone)]
pub struct Field {
    pub name: String,
    pub scalar_type: String,
    pub optional: bool,
    pub is_id: bool,
    pub is_unique: bool,
    pub default: Option<DefaultValue>,
}

#[derive(Debug, Clone)]
pub struct Index {
    pub columns: Vec<String>,
    pub unique: bool,
    pub name: Option<String>,
}

#[derive(Debug, Clone)]
pub enum DefaultValue {
    String(String),
    Number(String),
    Boolean(bool),
    CurrentTimestamp,
    Null,
}

pub fn parse_schema(input: &str) -> Result<Schema> {
    let lines = preprocess(input);
    let mut idx = 0usize;
    let mut models = Vec::new();

    while idx < lines.len() {
        let line = lines[idx].trim();
        if line.is_empty() {
            idx += 1;
            continue;
        }

        if line.starts_with("datasource ") || line.starts_with("generator ") {
            idx = skip_block(&lines, idx)?;
            continue;
        }

        if line.starts_with("model ") {
            let (model, next_idx) = parse_model(&lines, idx)?;
            models.push(model);
            idx = next_idx;
            continue;
        }

        bail!("Unsupported schema declaration: {line}");
    }

    if models.is_empty() {
        bail!("Schema does not contain any model blocks");
    }

    Ok(Schema { models })
}

impl Schema {
    pub fn to_sql(&self) -> Result<Vec<String>> {
        let mut sql = Vec::new();
        for model in &self.models {
            sql.push(model.create_table_sql()?);
            sql.extend(model.index_sql()?);
        }
        Ok(sql)
    }
}

impl Model {
    fn create_table_sql(&self) -> Result<String> {
        validate_identifier(&self.name)?;
        let mut columns = Vec::new();
        let mut has_primary_key = false;

        for field in &self.fields {
            validate_identifier(&field.name)?;
            if field.is_id {
                if has_primary_key {
                    bail!("Model '{}' contains multiple @id fields", self.name);
                }
                has_primary_key = true;
            }
            columns.push(field.column_sql()?);
        }

        if !has_primary_key {
            columns.insert(0, "\"id\" INTEGER PRIMARY KEY AUTOINCREMENT".to_string());
        }

        Ok(format!(
            "CREATE TABLE IF NOT EXISTS {} ({})",
            quote_identifier(&self.name),
            columns.join(", ")
        ))
    }

    fn index_sql(&self) -> Result<Vec<String>> {
        let mut statements = Vec::new();
        for (position, index) in self.indexes.iter().enumerate() {
            let name = index.name.clone().unwrap_or_else(|| {
                format!(
                    "idx_{}_{}_{}",
                    self.name.to_lowercase(),
                    if index.unique { "uniq" } else { "idx" },
                    position + 1
                )
            });
            validate_identifier(&name)?;
            let mut columns = Vec::new();
            for column in &index.columns {
                validate_identifier(column)?;
                columns.push(quote_identifier(column));
            }
            let uniqueness = if index.unique { "UNIQUE " } else { "" };
            statements.push(format!(
                "CREATE {}INDEX IF NOT EXISTS {} ON {} ({})",
                uniqueness,
                quote_identifier(&name),
                quote_identifier(&self.name),
                columns.join(", ")
            ));
        }
        Ok(statements)
    }
}

impl Field {
    fn column_sql(&self) -> Result<String> {
        let sqlite_type = sqlite_type(&self.scalar_type)?;
        if self.is_id {
            if self.scalar_type != "Int" && self.scalar_type != "BigInt" {
                bail!("@id fields must use Int or BigInt");
            }
            return Ok(format!(
                "{} INTEGER PRIMARY KEY AUTOINCREMENT",
                quote_identifier(&self.name)
            ));
        }

        let mut parts = vec![format!("{} {}", quote_identifier(&self.name), sqlite_type)];
        if !self.optional {
            parts.push("NOT NULL".to_string());
        }
        if let Some(default) = &self.default {
            parts.push(format!("DEFAULT {}", default.to_sql()));
        }
        if self.is_unique {
            parts.push("UNIQUE".to_string());
        }
        Ok(parts.join(" "))
    }
}

impl DefaultValue {
    fn to_sql(&self) -> String {
        match self {
            DefaultValue::String(value) => format!("'{}'", value.replace('\'', "''")),
            DefaultValue::Number(value) => value.clone(),
            DefaultValue::Boolean(value) => {
                if *value {
                    "1".to_string()
                } else {
                    "0".to_string()
                }
            }
            DefaultValue::CurrentTimestamp => "CURRENT_TIMESTAMP".to_string(),
            DefaultValue::Null => "NULL".to_string(),
        }
    }
}

fn preprocess(input: &str) -> Vec<String> {
    input
        .lines()
        .map(strip_inline_comment)
        .map(|line| line.trim().to_string())
        .collect()
}

fn strip_inline_comment(line: &str) -> String {
    let mut in_string = false;
    let chars: Vec<char> = line.chars().collect();
    let mut idx = 0usize;
    while idx < chars.len() {
        if chars[idx] == '"' {
            in_string = !in_string;
        }
        if !in_string && idx + 1 < chars.len() && chars[idx] == '/' && chars[idx + 1] == '/' {
            return chars[..idx].iter().collect();
        }
        idx += 1;
    }
    line.to_string()
}

fn skip_block(lines: &[String], start: usize) -> Result<usize> {
    let mut idx = start;
    let mut depth = 0i32;
    let mut opened = false;
    while idx < lines.len() {
        let line = &lines[idx];
        if line.contains('{') {
            depth += line.matches('{').count() as i32;
            opened = true;
        }
        if line.contains('}') {
            depth -= line.matches('}').count() as i32;
            if opened && depth <= 0 {
                return Ok(idx + 1);
            }
        }
        idx += 1;
    }
    bail!("Unterminated block starting at line {}", start + 1)
}

fn parse_model(lines: &[String], start: usize) -> Result<(Model, usize)> {
    let header = lines[start].trim();
    let name_part = header
        .strip_prefix("model ")
        .ok_or_else(|| anyhow!("Invalid model declaration: {header}"))?;
    let name = name_part
        .split('{')
        .next()
        .ok_or_else(|| anyhow!("Invalid model declaration: {header}"))?
        .trim();
    if name.is_empty() {
        bail!("Model declaration is missing a name: {header}");
    }
    validate_identifier(name)?;

    let mut idx = start;
    let mut opened = header.contains('{');
    if !opened {
        idx += 1;
        if idx >= lines.len() || lines[idx].trim() != "{" {
            bail!("Model '{}' must be followed by '{{'", name);
        }
        opened = true;
    }

    if !opened {
        bail!("Model '{}' has an invalid body", name);
    }

    idx += 1;
    let mut fields = Vec::new();
    let mut indexes = Vec::new();
    while idx < lines.len() {
        let line = lines[idx].trim();
        if line.is_empty() {
            idx += 1;
            continue;
        }
        if line == "}" {
            return Ok((
                Model {
                    name: name.to_string(),
                    fields,
                    indexes,
                },
                idx + 1,
            ));
        }
        if line.starts_with("@@") {
            indexes.push(parse_index(line)?);
        } else {
            fields.push(parse_field(line)?);
        }
        idx += 1;
    }
    bail!("Model '{}' is missing a closing '}}'", name)
}

fn parse_index(line: &str) -> Result<Index> {
    let (unique, remainder) = if let Some(rest) = line.strip_prefix("@@index") {
        (false, rest.trim())
    } else if let Some(rest) = line.strip_prefix("@@unique") {
        (true, rest.trim())
    } else {
        bail!("Unsupported model directive: {line}");
    };

    let open = remainder.find('(').ok_or_else(|| anyhow!("Invalid directive: {line}"))?;
    let close = remainder.rfind(')').ok_or_else(|| anyhow!("Invalid directive: {line}"))?;
    let body = &remainder[open + 1..close];
    let cols_open = body.find('[').ok_or_else(|| anyhow!("Directive is missing '[': {line}"))?;
    let cols_close = body.find(']').ok_or_else(|| anyhow!("Directive is missing ']': {line}"))?;
    let columns = body[cols_open + 1..cols_close]
        .split(',')
        .map(|item| item.trim().to_string())
        .filter(|item| !item.is_empty())
        .collect::<Vec<_>>();
    if columns.is_empty() {
        bail!("Directive must specify at least one column: {line}");
    }

    let mut name = None;
    if let Some(name_idx) = body.find("name:") {
        let value = body[name_idx + 5..].trim().trim_start_matches(',').trim();
        let value = value.trim_matches('"');
        if !value.is_empty() {
            name = Some(value.to_string());
        }
    }

    Ok(Index { columns, unique, name })
}

fn parse_field(line: &str) -> Result<Field> {
    let mut parts = line.split_whitespace();
    let name = parts.next().ok_or_else(|| anyhow!("Invalid field line: {line}"))?;
    let raw_type = parts.next().ok_or_else(|| anyhow!("Invalid field line: {line}"))?;

    validate_identifier(name)?;

    let optional = raw_type.ends_with('?');
    let scalar_type = raw_type.trim_end_matches('?').to_string();
    sqlite_type(&scalar_type)?;

    let mut is_id = false;
    let mut is_unique = false;
    let mut default = None;

    for attr in parts {
        if attr == "@id" {
            is_id = true;
        } else if attr == "@unique" {
            is_unique = true;
        } else if let Some(value) = attr.strip_prefix("@default(") {
            let inner = value.strip_suffix(')').ok_or_else(|| anyhow!("Malformed @default in line: {line}"))?;
            default = Some(parse_default(inner)?);
        } else {
            bail!("Unsupported field attribute '{attr}' in line: {line}");
        }
    }

    Ok(Field {
        name: name.to_string(),
        scalar_type,
        optional,
        is_id,
        is_unique,
        default,
    })
}

fn parse_default(value: &str) -> Result<DefaultValue> {
    let trimmed = value.trim();
    if trimmed.eq_ignore_ascii_case("true") {
        return Ok(DefaultValue::Boolean(true));
    }
    if trimmed.eq_ignore_ascii_case("false") {
        return Ok(DefaultValue::Boolean(false));
    }
    if trimmed.eq_ignore_ascii_case("null") {
        return Ok(DefaultValue::Null);
    }
    if trimmed.eq_ignore_ascii_case("now()") {
        return Ok(DefaultValue::CurrentTimestamp);
    }
    if trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2 {
        return Ok(DefaultValue::String(
            trimmed[1..trimmed.len() - 1].to_string(),
        ));
    }
    if trimmed.parse::<f64>().is_ok() {
        return Ok(DefaultValue::Number(trimmed.to_string()));
    }
    bail!("Unsupported default value: {trimmed}")
}

fn sqlite_type(scalar_type: &str) -> Result<&'static str> {
    match scalar_type {
        "String" => Ok("TEXT"),
        "Int" | "BigInt" => Ok("INTEGER"),
        "Float" | "Decimal" => Ok("REAL"),
        "Boolean" => Ok("INTEGER"),
        "Bytes" => Ok("BLOB"),
        "Json" | "DateTime" => Ok("TEXT"),
        other => bail!("Unsupported scalar type: {other}"),
    }
}

pub fn quote_identifier(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

pub fn validate_identifier(identifier: &str) -> Result<()> {
    let mut chars = identifier.chars();
    let Some(first) = chars.next() else {
        bail!("Identifier cannot be empty")
    };
    if !(first.is_ascii_alphabetic() || first == '_') {
        bail!("Invalid identifier: {identifier}");
    }
    if !chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_') {
        bail!("Invalid identifier: {identifier}");
    }
    Ok(())
}
