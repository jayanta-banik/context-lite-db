mod schema;

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, anyhow, bail};
use clap::{Args, Parser, Subcommand};
use rusqlite::types::{Value as SqlValue, ValueRef};
use rusqlite::{Connection, params_from_iter};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::schema::{parse_schema, quote_identifier, validate_identifier};

#[derive(Parser, Debug)]
#[command(name = "contextdb")]
#[command(about = "Rust-powered ContextDB core, schema tool, and CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    Init(InitArgs),
    Schema(SchemaArgs),
    Query(QueryArgs),
    Inspect(DbPathArgs),
    Insert(MutationArgs),
    Update(UpdateArgs),
    Delete(DeleteArgs),
    Rpc(DbPathArgs),
}

#[derive(Args, Debug)]
struct DbPathArgs {
    #[arg(long)]
    db: String,
}

#[derive(Args, Debug)]
struct InitArgs {
    #[arg(long, default_value = ".")]
    dir: String,
    #[arg(long, default_value = "context.schema")]
    schema: String,
    #[arg(long, default_value = "context.db")]
    db: String,
    #[arg(long)]
    force: bool,
}

#[derive(Args, Debug)]
struct SchemaArgs {
    #[command(subcommand)]
    command: SchemaCommand,
}

#[derive(Subcommand, Debug)]
enum SchemaCommand {
    Apply(SchemaApplyArgs),
}

#[derive(Args, Debug)]
struct SchemaApplyArgs {
    #[arg(long)]
    db: String,
    #[arg(long, default_value = "context.schema")]
    schema: String,
}

#[derive(Args, Debug)]
struct QueryArgs {
    #[arg(long)]
    db: String,
    #[arg(long)]
    sql: String,
    #[arg(long = "param")]
    params: Vec<String>,
}

#[derive(Args, Debug)]
struct MutationArgs {
    #[arg(long)]
    db: String,
    #[arg(long)]
    table: String,
    #[arg(long)]
    data: String,
}

#[derive(Args, Debug)]
struct UpdateArgs {
    #[arg(long)]
    db: String,
    #[arg(long)]
    table: String,
    #[arg(long)]
    data: String,
    #[arg(long)]
    r#where: String,
    #[arg(long = "param")]
    params: Vec<String>,
}

#[derive(Args, Debug)]
struct DeleteArgs {
    #[arg(long)]
    db: String,
    #[arg(long)]
    table: String,
    #[arg(long)]
    r#where: String,
    #[arg(long = "param")]
    params: Vec<String>,
}

#[derive(Deserialize)]
struct RpcRequest {
    action: String,
    #[serde(default)]
    params: Value,
}

#[derive(Serialize)]
struct RpcResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{err:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Init(args) => {
            let result = init_project(&args)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::Schema(args) => match args.command {
            SchemaCommand::Apply(apply_args) => {
                let result = apply_schema_file(&apply_args.db, &apply_args.schema)?;
                println!("{}", serde_json::to_string_pretty(&result)?);
            }
        },
        Commands::Query(args) => {
            let conn = open_connection(&args.db)?;
            let rows = query_rows(&conn, &args.sql, &args.params)?;
            println!("{}", serde_json::to_string_pretty(&rows)?);
        }
        Commands::Inspect(args) => {
            let conn = open_connection(&args.db)?;
            let inspection = inspect_database(&conn)?;
            println!("{}", serde_json::to_string_pretty(&inspection)?);
        }
        Commands::Insert(args) => {
            let conn = open_connection(&args.db)?;
            let data: BTreeMap<String, Value> = serde_json::from_str(&args.data)
                .context("--data must be a JSON object")?;
            let row_id = insert_row(&conn, &args.table, &data)?;
            println!("{}", json!({"row_id": row_id}));
        }
        Commands::Update(args) => {
            let conn = open_connection(&args.db)?;
            let data: BTreeMap<String, Value> = serde_json::from_str(&args.data)
                .context("--data must be a JSON object")?;
            let count = update_rows(&conn, &args.table, &data, &args.r#where, &args.params)?;
            println!("{}", json!({"rows_affected": count}));
        }
        Commands::Delete(args) => {
            let conn = open_connection(&args.db)?;
            let count = delete_rows(&conn, &args.table, &args.r#where, &args.params)?;
            println!("{}", json!({"rows_affected": count}));
        }
        Commands::Rpc(args) => {
            let request: RpcRequest = serde_json::from_reader(std::io::stdin())
                .context("Failed to parse JSON RPC request from stdin")?;
            let response = handle_rpc(&args.db, request);
            println!("{}", serde_json::to_string(&response)?);
            if !response.ok {
                std::process::exit(1);
            }
        }
    }
    Ok(())
}

fn handle_rpc(db_path: &str, request: RpcRequest) -> RpcResponse {
    match dispatch_rpc(db_path, request) {
        Ok(result) => RpcResponse {
            ok: true,
            result: Some(result),
            error: None,
        },
        Err(err) => RpcResponse {
            ok: false,
            result: None,
            error: Some(err.to_string()),
        },
    }
}

fn dispatch_rpc(db_path: &str, request: RpcRequest) -> Result<Value> {
    let conn = open_connection(db_path)?;
    match request.action.as_str() {
        "execute" => {
            let sql = required_string(&request.params, "sql")?;
            let params = optional_string_list(&request.params, "params")?;
            let changed = execute_statement(&conn, &sql, &params)?;
            Ok(json!({"rows_affected": changed}))
        }
        "query" => {
            let sql = required_string(&request.params, "sql")?;
            let params = optional_string_list(&request.params, "params")?;
            Ok(Value::Array(query_rows(&conn, &sql, &params)?))
        }
        "create_table" => {
            let table = required_string(&request.params, "table")?;
            let columns = required_map(&request.params, "columns")?;
            let if_not_exists = request
                .params
                .get("if_not_exists")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            create_table(&conn, &table, &columns, if_not_exists)?;
            Ok(json!({"ok": true}))
        }
        "insert" => {
            let table = required_string(&request.params, "table")?;
            let data = required_map(&request.params, "data")?;
            let row_id = insert_row(&conn, &table, &data)?;
            Ok(json!({"row_id": row_id}))
        }
        "batch_insert" => {
            let table = required_string(&request.params, "table")?;
            let rows = required_rows(&request.params, "rows")?;
            let ids = batch_insert(&conn, &table, &rows)?;
            Ok(json!(ids))
        }
        "update" => {
            let table = required_string(&request.params, "table")?;
            let data = required_map(&request.params, "data")?;
            let where_clause = required_string(&request.params, "where")?;
            let params = optional_string_list(&request.params, "params")?;
            let rows = update_rows(&conn, &table, &data, &where_clause, &params)?;
            Ok(json!({"rows_affected": rows}))
        }
        "batch_update" => {
            let table = required_string(&request.params, "table")?;
            let updates = request
                .params
                .get("updates")
                .and_then(Value::as_array)
                .ok_or_else(|| anyhow!("'updates' must be an array"))?;
            let rows = batch_update(&conn, &table, updates)?;
            Ok(json!({"rows_affected": rows}))
        }
        "delete" => {
            let table = required_string(&request.params, "table")?;
            let where_clause = required_string(&request.params, "where")?;
            let params = optional_string_list(&request.params, "params")?;
            let rows = delete_rows(&conn, &table, &where_clause, &params)?;
            Ok(json!({"rows_affected": rows}))
        }
        "batch_delete" => {
            let table = required_string(&request.params, "table")?;
            let conditions = request
                .params
                .get("conditions")
                .and_then(Value::as_array)
                .ok_or_else(|| anyhow!("'conditions' must be an array"))?;
            let rows = batch_delete(&conn, &table, conditions)?;
            Ok(json!({"rows_affected": rows}))
        }
        "drop_table" => {
            let table = required_string(&request.params, "table")?;
            drop_table(&conn, &table)?;
            Ok(json!({"ok": true}))
        }
        "truncate_table" => {
            let table = required_string(&request.params, "table")?;
            truncate_table(&conn, &table)?;
            Ok(json!({"ok": true}))
        }
        "apply_schema" => {
            let schema_path = required_string(&request.params, "schema_path")?;
            let result = apply_schema_file(db_path, &schema_path)?;
            Ok(result)
        }
        "inspect" => Ok(inspect_database(&conn)?),
        other => bail!("Unsupported RPC action: {other}"),
    }
}

fn open_connection(db_path: &str) -> Result<Connection> {
    if db_path == ":memory:" {
        bail!("The standalone ContextDB binary only supports file-backed SQLite databases");
    }
    if let Some(parent) = Path::new(db_path).parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create database directory '{}" , parent.display()))?;
        }
    }
    let conn = Connection::open(db_path)
        .with_context(|| format!("Failed to open SQLite database at '{db_path}'"))?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;
    Ok(conn)
}

fn init_project(args: &InitArgs) -> Result<Value> {
    let dir = Path::new(&args.dir);
    fs::create_dir_all(dir).with_context(|| format!("Failed to create '{}" , dir.display()))?;
    let schema_path = dir.join(&args.schema);
    let db_path = dir.join(&args.db);

    if schema_path.exists() && !args.force {
        bail!("Schema file already exists: {}", schema_path.display());
    }
    if db_path.exists() && !args.force {
        bail!("Database file already exists: {}", db_path.display());
    }

    if args.force || !schema_path.exists() {
        fs::write(&schema_path, default_schema())
            .with_context(|| format!("Failed to write '{}" , schema_path.display()))?;
    }
    let result = apply_schema_file(path_to_string(&db_path)?, path_to_string(&schema_path)?)?;
    Ok(json!({
        "schema_path": schema_path,
        "db_path": db_path,
        "schema_result": result,
    }))
}

fn default_schema() -> &'static str {
    r#"datasource db {
  provider = \"sqlite\"
  url      = \"file:./context.db\"
}

model Note {
  id        Int      @id
  title     String
  body      String?
  createdAt DateTime @default(now())

  @@index([title], name: \"idx_note_title\")
}
"#
}

fn path_to_string(path: &Path) -> Result<&str> {
    path.to_str().ok_or_else(|| anyhow!("Non-UTF8 path: {}", path.display()))
}

fn apply_schema_file(db_path: &str, schema_path: &str) -> Result<Value> {
    let schema_source = fs::read_to_string(schema_path)
        .with_context(|| format!("Failed to read schema file '{schema_path}'"))?;
    let schema = parse_schema(&schema_source)?;
    let statements = schema.to_sql()?;
    let conn = open_connection(db_path)?;
    for statement in &statements {
        conn.execute(statement, [])
            .with_context(|| format!("Failed to execute schema statement: {statement}"))?;
    }
    Ok(json!({
        "models": schema.models.iter().map(|model| model.name.clone()).collect::<Vec<_>>(),
        "statements": statements,
    }))
}

fn execute_statement(conn: &Connection, sql: &str, params: &[String]) -> Result<usize> {
    let changed = conn.execute(sql, params_from_iter(params.iter().map(|item| item.as_str())))?;
    Ok(changed)
}

fn query_rows(conn: &Connection, sql: &str, params: &[String]) -> Result<Vec<Value>> {
    let mut statement = conn.prepare(sql)?;
    let column_names = statement
        .column_names()
        .iter()
        .map(|name| (*name).to_string())
        .collect::<Vec<_>>();
    let rows = statement.query_map(params_from_iter(params.iter().map(|item| item.as_str())), |row| {
        let mut object = serde_json::Map::new();
        for (idx, name) in column_names.iter().enumerate() {
            object.insert(name.clone(), value_ref_to_json(row.get_ref(idx)?));
        }
        Ok(Value::Object(object))
    })?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row?);
    }
    Ok(result)
}

fn inspect_database(conn: &Connection) -> Result<Value> {
    let mut statement = conn.prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let table_names = statement.query_map([], |row| row.get::<_, String>(0))?;
    let mut tables = Vec::new();
    for table_name in table_names {
        let table_name = table_name?;
        let pragma = format!("PRAGMA table_info({})", quote_identifier(&table_name));
        let columns = query_rows(conn, &pragma, &[])?;
        tables.push(json!({
            "name": table_name,
            "columns": columns,
        }));
    }
    Ok(json!({"tables": tables}))
}

fn create_table(
    conn: &Connection,
    table: &str,
    columns: &BTreeMap<String, Value>,
    if_not_exists: bool,
) -> Result<()> {
    validate_identifier(table)?;
    let mut defs = Vec::new();
    for (name, value) in columns {
        validate_identifier(name)?;
        let sql_type = value
            .as_str()
            .ok_or_else(|| anyhow!("Column type for '{}' must be a string", name))?;
        defs.push(format!("{} {}", quote_identifier(name), sql_type));
    }
    let guard = if if_not_exists { "IF NOT EXISTS " } else { "" };
    let sql = format!(
        "CREATE TABLE {}{} (\"id\" INTEGER PRIMARY KEY AUTOINCREMENT, {})",
        guard,
        quote_identifier(table),
        defs.join(", ")
    );
    conn.execute(&sql, [])?;
    Ok(())
}

fn insert_row(conn: &Connection, table: &str, data: &BTreeMap<String, Value>) -> Result<i64> {
    validate_identifier(table)?;
    if data.is_empty() {
        bail!("Insert data cannot be empty");
    }
    let mut columns = Vec::new();
    let mut placeholders = Vec::new();
    let mut values = Vec::new();
    for (name, value) in data {
        validate_identifier(name)?;
        columns.push(quote_identifier(name));
        placeholders.push("?".to_string());
        values.push(json_to_sql_value(value));
    }
    let sql = format!(
        "INSERT INTO {} ({}) VALUES ({})",
        quote_identifier(table),
        columns.join(", "),
        placeholders.join(", ")
    );
    conn.execute(&sql, params_from_iter(values))?;
    Ok(conn.last_insert_rowid())
}

fn batch_insert(conn: &Connection, table: &str, rows: &[BTreeMap<String, Value>]) -> Result<Vec<i64>> {
    let transaction = conn.unchecked_transaction()?;
    let mut ids = Vec::new();
    for row in rows {
        ids.push(insert_row(&transaction, table, row)?);
    }
    transaction.commit()?;
    Ok(ids)
}

fn update_rows(
    conn: &Connection,
    table: &str,
    data: &BTreeMap<String, Value>,
    where_clause: &str,
    params: &[String],
) -> Result<usize> {
    validate_identifier(table)?;
    if data.is_empty() {
        bail!("Update data cannot be empty");
    }
    let mut assignments = Vec::new();
    let mut sql_params = Vec::new();
    for (name, value) in data {
        validate_identifier(name)?;
        assignments.push(format!("{} = ?", quote_identifier(name)));
        sql_params.push(json_to_sql_value(value));
    }
    sql_params.extend(params.iter().map(|param| SqlValue::Text(param.clone())));
    let sql = format!(
        "UPDATE {} SET {} WHERE {}",
        quote_identifier(table),
        assignments.join(", "),
        where_clause
    );
    Ok(conn.execute(&sql, params_from_iter(sql_params))?)
}

fn batch_update(conn: &Connection, table: &str, updates: &[Value]) -> Result<usize> {
    let transaction = conn.unchecked_transaction()?;
    let mut total = 0usize;
    for update in updates {
        let data = required_map(update, "data")?;
        let where_clause = required_string(update, "where")?;
        let params = optional_string_list(update, "params")?;
        total += update_rows(&transaction, table, &data, &where_clause, &params)?;
    }
    transaction.commit()?;
    Ok(total)
}

fn delete_rows(conn: &Connection, table: &str, where_clause: &str, params: &[String]) -> Result<usize> {
    validate_identifier(table)?;
    let sql = format!("DELETE FROM {} WHERE {}", quote_identifier(table), where_clause);
    Ok(conn.execute(&sql, params_from_iter(params.iter().map(|item| item.as_str())))?)
}

fn batch_delete(conn: &Connection, table: &str, conditions: &[Value]) -> Result<usize> {
    let transaction = conn.unchecked_transaction()?;
    let mut total = 0usize;
    for condition in conditions {
        let where_clause = required_string(condition, "where")?;
        let params = optional_string_list(condition, "params")?;
        total += delete_rows(&transaction, table, &where_clause, &params)?;
    }
    transaction.commit()?;
    Ok(total)
}

fn drop_table(conn: &Connection, table: &str) -> Result<()> {
    validate_identifier(table)?;
    let sql = format!("DROP TABLE IF EXISTS {}", quote_identifier(table));
    conn.execute(&sql, [])?;
    Ok(())
}

fn truncate_table(conn: &Connection, table: &str) -> Result<()> {
    validate_identifier(table)?;
    let sql = format!("DELETE FROM {}", quote_identifier(table));
    conn.execute(&sql, [])?;
    Ok(())
}

fn required_string(value: &Value, key: &str) -> Result<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .ok_or_else(|| anyhow!("'{key}' must be a string"))
}

fn optional_string_list(value: &Value, key: &str) -> Result<Vec<String>> {
    match value.get(key) {
        None => Ok(Vec::new()),
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                item.as_str()
                    .map(ToString::to_string)
                    .ok_or_else(|| anyhow!("'{key}' entries must be strings"))
            })
            .collect(),
        Some(_) => bail!("'{key}' must be an array of strings"),
    }
}

fn required_map(value: &Value, key: &str) -> Result<BTreeMap<String, Value>> {
    let map = value
        .get(key)
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow!("'{key}' must be an object"))?;
    Ok(map.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
}

fn required_rows(value: &Value, key: &str) -> Result<Vec<BTreeMap<String, Value>>> {
    let rows = value
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("'{key}' must be an array"))?;
    rows.iter()
        .map(|row| {
            row.as_object()
                .map(|object| object.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
                .ok_or_else(|| anyhow!("'{key}' entries must be objects"))
        })
        .collect()
}

fn json_to_sql_value(value: &Value) -> SqlValue {
    match value {
        Value::Null => SqlValue::Null,
        Value::Bool(boolean) => SqlValue::Integer(if *boolean { 1 } else { 0 }),
        Value::Number(number) => {
            if let Some(integer) = number.as_i64() {
                SqlValue::Integer(integer)
            } else if let Some(float) = number.as_f64() {
                SqlValue::Real(float)
            } else {
                SqlValue::Text(number.to_string())
            }
        }
        Value::String(text) => SqlValue::Text(text.clone()),
        Value::Array(_) | Value::Object(_) => SqlValue::Text(value.to_string()),
    }
}

fn value_ref_to_json(value: ValueRef<'_>) -> Value {
    match value {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(integer) => Value::Number(integer.into()),
        ValueRef::Real(real) => serde_json::Number::from_f64(real)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        ValueRef::Text(text) => Value::String(String::from_utf8_lossy(text).into_owned()),
        ValueRef::Blob(blob) => Value::Array(blob.iter().copied().map(|byte| Value::Number(byte.into())).collect()),
    }
}
