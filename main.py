import os
import base64
from io import BytesIO
from datetime import datetime
import calendar


import psycopg2
import qrcode
from flask import Flask, request, jsonify
from flask_cors import CORS


# ==========================
# APP CONFIG
# ==========================

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")
UPI_ID = os.environ.get("UPI_ID")

if not DATABASE_URL:
    raise Exception("DATABASE_URL not set")

if not UPI_ID:
    raise Exception("UPI_ID not set")


# ==========================
# DATABASE
# ==========================

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # SOLD TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sold (
            id SERIAL PRIMARY KEY,
            credits_sold FLOAT NOT NULL,
            discount_percent FLOAT NOT NULL,
            final_price FLOAT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # REDEEMED TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS redeemed (
            id SERIAL PRIMARY KEY,
            credits_used FLOAT NOT NULL,
            time_used VARCHAR NOT NULL,
            date DATE NOT NULL
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()


# ==========================
# ROUTES
# ==========================

@app.route("/")
def health_check():
    return jsonify({"status": "API running"})


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json()

    try:
        credits = float(data.get("credits", 0))
        discount = float(data.get("discount", 0))
    except:
        return jsonify({"error": "Invalid input"}), 400

    if credits <= 0 or discount < 0:
        return jsonify({"error": "Invalid values"}), 400

    discount_amt = (discount * credits) / 100
    final_amount = credits - discount_amt

    return jsonify({"final_amount": round(final_amount, 2)})


@app.route("/sell", methods=["POST"])
def sell():
    data = request.get_json()

    try:
        credits = float(data.get("credits", 0))
        discount = float(data.get("discount", 0))
        final_amount = float(data.get("final_amount", 0))
    except:
        return jsonify({"error": "Invalid input"}), 400

    if credits <= 0 or final_amount <= 0:
        return jsonify({"error": "Invalid values"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sold (credits_sold, discount_percent, final_price)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (credits, discount, final_amount))

    new_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "success", "id": new_id})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.get_json()

    try:
        credits_used = float(data.get("credits_used", 0))
        time_used=data.get("meal_time")
        date_used=data.get("date_used")
    except:
        return jsonify({"error": "Invalid input"}), 400

    if credits_used <= 0:
        return jsonify({"error": "Invalid value"}), 400

    now = datetime.now()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO redeemed (credits_used, time_used, date)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (credits_used, time_used, now.date()))

    new_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "success", "id": new_id})


@app.route("/generate_qr", methods=["POST"])
def generate_qr():
    data = request.get_json()

    try:
        amount = float(data.get("latest_amount", 0))
    except:
        return jsonify({"error": "Invalid input"}), 400

    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    link = f"upi://pay?pa={UPI_ID}&am={amount}"

    qr = qrcode.make(link)

    buffer = BytesIO()
    qr.save(buffer, format="PNG")

    img_str = base64.b64encode(buffer.getvalue()).decode()

    return jsonify({"qr_image": img_str})



@app.route("/report", methods=["GET"])
def report():

    conn = get_db_connection()
    cur = conn.cursor()

    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    cur.execute("""
        SELECT
        (SELECT SUM(credits_sold) FROM sold),
        (SELECT SUM(credits_used) FROM redeemed)
    """)

    sold_total, used_total = cur.fetchone()

    sold_total = sold_total or 0
    used_total = used_total or 0

    total_credits = days_in_month * 250
    left_credits = total_credits - (used_total + sold_total)

    progress = round(((used_total + sold_total) / total_credits) * 100)

    cur.close()
    conn.close()

    return jsonify({
        "used": used_total,
        "sold": sold_total,
        "left": left_credits,
        "progress": progress
    })



# ==========================
# ENTRY
# ==========================

if __name__ == "__main__":
    app.run()