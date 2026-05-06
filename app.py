from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
db = SQLAlchemy(app)

# ------------------ MODELS ------------------

class Crate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crate_number = db.Column(db.String(50), unique=True, nullable=False)
    location = db.Column(db.String(50), nullable=False)
    product_type = db.Column(db.String(20), nullable=False)  # "3 inserts" or "4 inserts"
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('CrateProduct', backref='crate', cascade="all, delete", lazy=True)


class CrateProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crate_id = db.Column(db.Integer, db.ForeignKey('crate.id'), nullable=True)  # ✅ allow NULL
    product_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="in_crate")  # NEW

# ------------------ HELPERS ------------------

def get_max_capacity(product_type):
    return 12 if product_type == "3 inserts" else 9


# ------------------ ROUTES ------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/add_or_update', methods=['POST'])
def add_or_update():
    try:
        data = request.json
        print("Incoming data:", data)  # 👈 DEBUG

        products = data.get('products', [])
        product_type = data.get('product_type')

        if not product_type:
            return jsonify({"error": "Product type missing"}), 400

        max_capacity = 12 if product_type == "3 inserts" else 9

        if len(products) > max_capacity:
            return jsonify({"error": f"Max capacity is {max_capacity}"}), 400

        crate = Crate.query.filter_by(crate_number=data['crate_number']).first()

        if crate:
            crate.location = data['location']
            crate.product_type = product_type
            crate.last_updated = datetime.utcnow()
            CrateProduct.query.filter_by(crate_id=crate.id).delete()
        else:
            crate = Crate(
                crate_number=data['crate_number'],
                location=data['location'],
                product_type=product_type
            )
            db.session.add(crate)
            db.session.flush()

        for product in products:
            db.session.add(CrateProduct(
                crate_id=crate.id,
                product_number=product,
                status="in_crate"
            ))

        db.session.commit()

        return jsonify({"message": "Updated successfully"})

    except Exception as e:
        print("ERROR:", str(e))  # 👈 THIS IS KEY
        return jsonify({"error": str(e)}), 500


@app.route('/get_crate/<crate_number>')
def get_crate(crate_number):
    crate = Crate.query.filter_by(crate_number=crate_number).first()

    if not crate:
        return jsonify({"error": "Not found"}), 404

    products = [p.product_number for p in crate.products]

    return jsonify({
        "crate_number": crate.crate_number,
        "location": crate.location,
        "product_type": crate.product_type,
        "products": products,
        "last_updated": crate.last_updated.strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/view_crate/<crate_number>')
def view_crate(crate_number):
    crate = Crate.query.filter_by(crate_number=crate_number).first()

    if not crate:
        return "Crate not found", 404

    products = [p.product_number for p in crate.products]

    return render_template("view_crate.html",
                           crate=crate,
                           products=products)


@app.route('/find_by_product/<product_number>')
def find_by_product(product_number):
    records = CrateProduct.query.filter_by(product_number=product_number).all()

    if not records:
        return jsonify({"error": "Product not found"}), 404

    results = []

    for r in records:
        if r.status == "in_crate":
            crate = Crate.query.get(r.crate_id)
            results.append({
                "status": "in_crate",
                "crate_number": crate.crate_number,
                "location": crate.location
            })
        else:
            results.append({
                "status": r.status
            })

    return jsonify({"results": results})


@app.route('/add_product_status', methods=['POST'])
def add_product_status():
    data = request.json

    product_number = data.get('product_number')
    status = data.get('status')

    if status not in ["held", "rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    # Remove if already exists anywhere
    existing = CrateProduct.query.filter_by(product_number=product_number).first()
    if existing:
        db.session.delete(existing)

    new_product = CrateProduct(
        crate_id=None,
        product_number=product_number,
        status=status
    )

    db.session.add(new_product)
    db.session.commit()

    return jsonify({"message": f"Product marked as {status}"})


# 🔥 GENERATE QR + PRINT DATA
@app.route('/generate_label/<crate_number>')
def generate_label(crate_number):
    crate = Crate.query.filter_by(crate_number=crate_number).first()

    if not crate:
        return "Not found", 404

    products = [p.product_number for p in crate.products]

    # Create QR code (link to crate info)
    qr_data = url_for('view_crate', crate_number=crate_number, _external=True)
    qr = qrcode.make(qr_data)

    qr_path = f"static/{crate_number}.png"
    qr.save(qr_path)

    return render_template("label.html",
                           crate=crate,
                           products=products,
                           qr_path=qr_path)


# ------------------ RUN ------------------

if __name__ == '__main__':
    os.makedirs("static", exist_ok=True)
    with app.app_context():
        db.create_all()
    if __name__ == '__main__':
        os.makedirs("static", exist_ok=True)
        with app.app_context():
            db.create_all()
        app.run()