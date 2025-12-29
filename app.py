import mysql.connector
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
app = Flask(__name__)

app.secret_key = "super_secret_key"

# ================= DATABASE CONNECTIONS =================
def main_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aruna@vpm32", 
        database="main_admin_db"
    )

def admin_db():
    db_name = session.get("admin_db", "main_admin_db") 
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aruna@vpm32",
        database=db_name
    )
    
# ================= LOGIN REQUIRED DECORATOR =================
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "role" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrap

# ================= ROUTES =================

@app.route("/")
def home():
    return redirect("/login")

# --- SIGNUP (Only for New Admins) ---
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        db_name = f"inventory_{username}"

        try:
            db = main_db()
            cur = db.cursor()
            
            # Create Database
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            
            # Register Admin
            cur.execute("INSERT INTO admins(username,password,db_name) VALUES(%s,%s,%s)", 
                        (username, password, db_name))
            db.commit()
            
            # Setup Admin Tables
            adb = mysql.connector.connect(host="localhost", user="root", password="Aruna@vpm32", database=db_name)
            acur = adb.cursor()
            
            # Products Table (Added Location)
            acur.execute("""CREATE TABLE IF NOT EXISTS products(
                            id INT AUTO_INCREMENT PRIMARY KEY, 
                            name VARCHAR(100), 
                            quantity INT, 
                            price FLOAT, 
                            unit VARCHAR(20),
                            location VARCHAR(100) DEFAULT 'General')""")
            
            acur.execute("CREATE TABLE IF NOT EXISTS sales(id INT AUTO_INCREMENT PRIMARY KEY, product_id INT, quantity INT, total FLOAT, date DATETIME DEFAULT CURRENT_TIMESTAMP)")
            
            # Users Table (Added Login/Logout Tracking)
            acur.execute("""CREATE TABLE IF NOT EXISTS users(
                            id INT AUTO_INCREMENT PRIMARY KEY, 
                            username VARCHAR(100) UNIQUE, 
                            password VARCHAR(255), 
                            role VARCHAR(20) DEFAULT 'user',
                            last_login DATETIME,
                            last_logout DATETIME)""")
            
            acur.execute("""
            CREATE TABLE IF NOT EXISTS store_profile(
                id INT PRIMARY KEY DEFAULT 1,
                store_name VARCHAR(100),
                address TEXT,
                phone VARCHAR(20),
                gstin VARCHAR(20),
                logo_url VARCHAR(255)
            )""")
            acur.execute("INSERT IGNORE INTO store_profile(id) VALUES(1)")

            adb.commit()
            adb.close()
            return redirect("/login")
        except Exception as e:
            return f"Error: {e}"

    return render_template("signup.html")

# --- LOGIN (Updated with Time Tracking) ---
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        role = request.form["role"]
        admin_name = request.form["admin_name"] 
        password = request.form["password"]
        
        # 1. Check Main DB for Admin existence
        db = main_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM admins WHERE username=%s", (admin_name,))
        admin_data = cur.fetchone()
        db.close()

        if not admin_data:
            return render_template("login.html", error="Admin/Store not found!")

        # === ADMIN LOGIN ===
        if role == "admin":
            if check_password_hash(admin_data["password"], password):
                session["role"] = "admin"
                session["user"] = admin_data["username"]
                session["admin_db"] = admin_data["db_name"]
                return redirect("/dashboard")
            else:
                error = "Incorrect Admin Password"

        # === USER LOGIN (With Time Tracking) ===
        elif role == "user":
            user_name = request.form.get("user_name")
            
            # Connect to that Admin's DB to check user
            try:
                udb = mysql.connector.connect(host="localhost", user="root", password="Aruna@vpm32", database=admin_data["db_name"])
                ucur = udb.cursor(dictionary=True)
                ucur.execute("SELECT * FROM users WHERE username=%s", (user_name,))
                user_data = ucur.fetchone()

                if user_data and check_password_hash(user_data["password"], password):
                    session["role"] = "user"
                    session["user"] = user_data["username"]
                    session["admin_db"] = admin_data["db_name"] # Use Admin's DB
                    
                    # --- UPDATE LOGIN TIME ---
                    ucur.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user_data['id'],))
                    udb.commit()
                    udb.close()
                    
                    return redirect("/dashboard")
                else:
                    udb.close()
                    error = "Invalid User Credentials"
            except:
                error = "Database Connection Error"

    return render_template("login.html", error=error)

# --- DASHBOARD ---
@app.route("/dashboard")
@login_required
def dashboard():
    db = admin_db()
    cur = db.cursor()
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(quantity) FROM products")
    total_stock = cur.fetchone()[0] or 0
    
    cur.execute("SELECT SUM(total) FROM sales")
    total_revenue = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM products WHERE quantity < 5")
    low_stock = cur.fetchone()[0]

    cur.execute("SELECT SUM(total) FROM sales WHERE DATE(date) = CURDATE()")
    today_sales = cur.fetchone()[0] or 0
    
    db.close()
    
    return render_template("dashboard.html", 
                           total_products=total_products, 
                           total_stock=total_stock, 
                           total_revenue=round(total_revenue, 2), 
                           low_stock=low_stock,
                           today_sales=round(today_sales, 2))

# --- PRODUCTS ---
@app.route("/products")
@login_required
def products():
    db = admin_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    db.close()
    return render_template("products.html", products=products)

# --- PROFILE & STAFF LIST ---
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if session["role"] != "admin":
        return redirect("/dashboard")
    db = admin_db()
    cur = db.cursor(dictionary=True)
    
    if request.method == "POST":
        name, addr = request.form["store_name"], request.form["address"]
        phone, gst = request.form["phone"], request.form["gstin"]
        cur.execute("REPLACE INTO store_profile(id, store_name, address, phone, gstin) VALUES(1, %s, %s, %s, %s)", 
                    (name, addr, phone, gst))
        db.commit()
        flash("Profile Updated!")

    cur.execute("SELECT * FROM store_profile WHERE id=1")
    store = cur.fetchone()
    # Staff list (Basic)
    cur.execute("SELECT id, username, role FROM users") 
    staff = cur.fetchall()
    db.close()
    return render_template("profile.html", store=store, staff=staff)

# --- ADMIN: USER ACTIVITY MONITOR ---
@app.route("/manage_users")
@login_required
def manage_users():
    if session["role"] != "admin":
        return redirect("/dashboard")
        
    db = admin_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    db.close()
    
    return render_template("manage_users.html", users=users)

# --- DELETE USER ---
@app.route("/delete_user/<int:id>")
@login_required
def delete_user(id):
    if session.get("role") != "admin":
        return redirect("/dashboard")

    db = admin_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id=%s", (id,))
        db.commit()
        flash("Staff member removed successfully!")
    except Exception as e:
        flash(f"Error: {e}")
    finally:
        db.close()
    
    return redirect("/profile")

# --- ADD  ---
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    # Admin check
    if session.get('role') != 'admin':
        flash("Access Denied! Admins only.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])
        unit = request.form['unit']
        location = request.form.get('location') or "Not Assigned"

        db_conn = admin_db() 
        cur = db_conn.cursor(dictionary=True, buffered=True)

        try:
            cur.execute("SELECT * FROM products WHERE name = %s", (name,))
            existing_product = cur.fetchone()

            if existing_product:
                new_qty = existing_product['quantity'] + quantity
                cur.execute("""
                    UPDATE products 
                    SET quantity = %s, price = %s, unit = %s, location = %s 
                    WHERE id = %s
                """, (new_qty, price, unit, location, existing_product['id']))
                flash(f"Updated {name}. New Qty: {new_qty}", "success")
            else:
                cur.execute("""
                    INSERT INTO products (name, quantity, price, unit, location) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, quantity, price, unit, location))
                flash(f"New product {name} added!", "success")
                
            db_conn.commit()

        except Exception as e:
            db_conn.rollback()
            flash(f"Error: {str(e)}", "error")
        finally:
            cur.close()
            db_conn.close()

        return redirect(url_for('products'))

    return render_template('add.html')

# --- EDIT PRODUCT (UPDATED with Location) ---
@app.route("/edit/<int:id>", methods=["GET","POST"])
@login_required
def edit(id):
    if session["role"] != "admin":
        return redirect("/products") 

    db = admin_db()
    cur = db.cursor(dictionary=True)

    if request.method == "POST":
        cur.execute("UPDATE products SET name=%s, quantity=%s, price=%s, location=%s WHERE id=%s",
                    (request.form["name"], request.form["quantity"], request.form["price"], request.form["location"], id))
        db.commit()
        db.close()
        return redirect("/products")

    cur.execute("SELECT * FROM products WHERE id=%s", (id,))
    product = cur.fetchone()
    db.close()
    return render_template("edit.html", product=product)

# --- CREATE USER ---
@app.route("/create_user", methods=["GET","POST"])
@login_required
def create_user():
    if session["role"] != "admin":
        return redirect("/dashboard")

    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        
        db = admin_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO users(username,password) VALUES(%s,%s)", (username, password))
            db.commit()
            return redirect("/dashboard")
        except:
            return "User already exists"
        finally:
            db.close()
            
    return render_template("create_user.html")

# --- SALES ---
@app.route("/sales")
@login_required
def sales():
    db = admin_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT s.id, p.name, s.quantity, s.total, s.date 
        FROM sales s 
        JOIN products p ON s.product_id=p.id 
        ORDER BY s.date DESC
    """)
    sales_data = cur.fetchall()
    for s in sales_data:
        s['date'] = str(s['date']) 
    db.close()
    return render_template("sales.html", sales=sales_data)

# --- CHARTS ---
@app.route("/charts")
@login_required
def charts():
    db = admin_db()
    cur = db.cursor(dictionary=True)
    
    # 1. Stock Data
    cur.execute("SELECT name, quantity FROM products LIMIT 10")
    stock_data = cur.fetchall()
    
    # 2. Sales Data
    cur.execute("""
        SELECT p.name, SUM(s.quantity) as total_sold 
        FROM sales s 
        JOIN products p ON s.product_id = p.id 
        GROUP BY p.name 
        ORDER BY total_sold DESC LIMIT 5
    """)
    sales_data = cur.fetchall()
    db.close()

    p_names = [x['name'] for x in stock_data]
    p_qty = [x['quantity'] for x in stock_data]
    s_names = [x['name'] for x in sales_data]
    s_qty = [x['total_sold'] for x in sales_data]

    return render_template("charts.html", p_names=p_names, p_qty=p_qty, s_names=s_names, s_qty=s_qty)

# --- BILLING ---
@app.route("/billing")
@login_required
def billing():
    db = admin_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE quantity > 0")
    products = cur.fetchall()
    cur.execute("SELECT * FROM store_profile WHERE id=1")
    store = cur.fetchone()
    db.close()
    return render_template("billing.html", products=products, store=store)

# --- SAVE BILL API ---
@app.route("/save_bill", methods=["POST"])
@login_required
def save_bill():
    data = request.json
    cart = data.get('cart')
    
    db = admin_db()
    cur = db.cursor()
    try:
        for item in cart:
            cur.execute("""
                INSERT INTO sales(product_id, quantity, total, date) 
                VALUES(%s, %s, %s, CURRENT_TIMESTAMP)
            """, (item['id'], item['qty'], item['total']))
            cur.execute("UPDATE products SET quantity = quantity - %s WHERE id=%s", (item['qty'], item['id']))
        
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# --- LOGOUT  ---
@app.route("/logout")
def logout():
    if "user" in session and "admin_db" in session:
        # Track Logout Time
        try:
            db = admin_db()
            cur = db.cursor()
            cur.execute("UPDATE users SET last_logout=NOW() WHERE username=%s", (session["user"],))
            db.commit()
            db.close()
        except:
            pass # Ignore errors if user table not found
            
    session.clear()
    return redirect("/login")

# ================= STEP 1: DB UPGRADE ROUTE =================
@app.route("/upgrade_db_v2")
def upgrade_db_v2():
    db = admin_db()
    cur = db.cursor()
    try:
        # 1. Add Location to Products
        cur.execute("ALTER TABLE products ADD COLUMN location VARCHAR(100) DEFAULT 'General'")
    except:
        pass # Already exists
        
    try:
        # 2. Add Login/Logout tracking to Users
        cur.execute("ALTER TABLE users ADD COLUMN last_login DATETIME")
        cur.execute("ALTER TABLE users ADD COLUMN last_logout DATETIME")
    except:
        pass # Already exists
    
    db.commit()
    db.close()
    return "Database Checked & Updated Successfully!"
        
if __name__ == "__main__":
    app.run(debug=True)