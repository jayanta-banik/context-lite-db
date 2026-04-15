# Relational Operations

ContextDB exposes the full power of SQLite through two complementary APIs:

1. **Prisma-style table access** – `db.table_name.create(...)` etc.
2. **Low-level helpers** – `db.execute(sql)`, `db.query(sql)`,
   `db.insert(table, data)`, …

---

## Creating tables

```python
db.create_table("products", {
    "name":     "TEXT",
    "price":    "REAL",
    "in_stock": "INTEGER",
})
```

An `id INTEGER PRIMARY KEY AUTOINCREMENT` column is added automatically.

---

## Prisma-style CRUD

Access any table as an attribute on `db`:

```python
# Create
product_id = db.products.create({"name": "Widget", "price": 9.99, "in_stock": 100})

# Create many (single transaction)
ids = db.products.create_many([
    {"name": "Gadget", "price": 19.99, "in_stock": 50},
    {"name": "Doohickey", "price": 4.99, "in_stock": 200},
])

# Seed a table with initial data
db.products.seed_table([
    {"name": "Alpha", "price": 1.00, "in_stock": 10},
    {"name": "Beta",  "price": 2.00, "in_stock": 20},
])

# Read
all_products   = db.products.find_all()
cheap_products = db.products.find_many("price < ?", [10.0])
first_cheap    = db.products.find_first("price < ?", [10.0])

# Update
db.products.update({"in_stock": 0}, where="name = ?", params=["Widget"])

# Batch update (multiple WHERE clauses in one transaction)
db.products.update_many([
    {"data": {"price": 8.99},  "where": "name = ?", "params": ["Widget"]},
    {"data": {"price": 17.99}, "where": "name = ?", "params": ["Gadget"]},
])

# Delete
db.products.delete("in_stock = ?", [0])

# Batch delete
db.products.delete_many([
    {"where": "name = ?", "params": ["Alpha"]},
    {"where": "name = ?", "params": ["Beta"]},
])
```

---

## Table-level operations

```python
# Remove all rows, keep the schema
db.products.truncate()
# or: db.truncate_table("products")

# Drop the table entirely
db.products.drop()
# or: db.drop_table("products")
```

---

## Low-level SQL

```python
# Raw SQL execution
db.execute("CREATE INDEX IF NOT EXISTS idx_price ON products(price)")

# Parameterised SELECT
rows = db.query("SELECT name, price FROM products WHERE price < ?", [5.0])

# Convenience helpers that mirror the table proxy
db.insert("products", {"name": "Foo", "price": 1.0, "in_stock": 5})
db.update("products", {"in_stock": 0}, "name = ?", ["Foo"])
db.delete("products", "name = ?", ["Foo"])
```
