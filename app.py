from flask import Flask, render_template, request, redirect, Response, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # use a strong random key in production


# Initialize the database and table
def init_db():
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'expenses.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create the expenses table if it doesn't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL
        )
    ''')

    # Check if 'category' column exists before altering
    c.execute("PRAGMA table_info(expenses)")
    columns = [col[1] for col in c.fetchall()]
    if 'category' not in columns:
        c.execute('ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT "Others"')

    # Create the users table if it doesn't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()


init_db()
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = sqlite3.connect('expenses.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            conn.commit()
            flash('Registration successful! Please log in.')
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash('Username already exists. Try a different one.')
            return redirect('/register')
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('expenses.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect('/')
        else:
            flash('Invalid credentials. Try again.')
            return redirect('/login')
    return render_template('login.html')

@app.route('/logout',methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()

    # Get optional date range filters from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        # Filter expenses by date range
        cursor.execute('SELECT * FROM expenses WHERE date BETWEEN ? AND ?', (start_date, end_date))
        expenses = cursor.fetchall()

        # Bar chart data (grouped by date within range)
        cursor.execute('SELECT date, SUM(amount) FROM expenses WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date',
                       (start_date, end_date))
        chart_data = cursor.fetchall()

        # Pie chart data (grouped by category within range)
        cursor.execute('SELECT category, SUM(amount) FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category',
                       (start_date, end_date))
        category_data = cursor.fetchall()
    else:
        # Show all data if no filters
        cursor.execute('SELECT * FROM expenses')
        expenses = cursor.fetchall()

        cursor.execute('SELECT date, SUM(amount) FROM expenses GROUP BY date ORDER BY date')
        chart_data = cursor.fetchall()

        cursor.execute('SELECT category, SUM(amount) FROM expenses GROUP BY category')
        category_data = cursor.fetchall()

    # Prepare labels and values
    labels = [row[0] for row in chart_data]
    values = [row[1] for row in chart_data]

    cat_labels = [row[0] for row in category_data]
    cat_values = [row[1] for row in category_data]

    conn.close()

    return render_template('home.html',
                           expenses=expenses,
                           labels=labels,
                           values=values,
                           cat_labels=cat_labels,
                           cat_values=cat_values)



@app.route('/add', methods=['POST'])
def add():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    description = request.form['description']
    amount = float(request.form['amount'])
    date = request.form['date']
    category = request.form['category']  # new line

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('INSERT INTO expenses (description, amount, date, category) VALUES (?, ?, ?, ?)', 
              (description, amount, date, category))
    conn.commit()
    conn.close()
    return redirect('/')


@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('DELETE FROM expenses WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/edit/<int:id>')
def edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('SELECT * FROM expenses WHERE id = ?', (id,))
    expense = c.fetchone()
    conn.close()
    return render_template('edit.html', expense=expense)

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    description = request.form['description']
    amount = float(request.form['amount'])
    date = request.form['date']
    category = request.form['category']

    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('UPDATE expenses SET description = ?, amount = ?, date = ?, category = ? WHERE id = ?', 
              (description, amount, date, category, id))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/export')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM expenses')
    rows = cursor.fetchall()
    conn.close()

    def generate():
        yield 'ID,Description,Amount,Date,Category\n'
        for row in rows:
            yield f'{row[0]},"{row[1]}",{row[2]},"{row[3]}","{row[4]}"\n'

    return Response(generate(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=expenses.csv"})



if __name__ == '__main__':
    app.run(debug=True)


