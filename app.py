from flask import Flask, jsonify, request, send_from_directory, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
import os

app = Flask(__name__)

# Настройки подключения к базе данных SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bikeshop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Swagger UI настройки
SWAGGER_URL = '/swagger'
API_URL = '/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={'app_name': "Bike Shop API"})
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Переадресация с главной страницы на Swagger
@app.route('/')
def index():
    return redirect(SWAGGER_URL)

# Сервис для отображения спецификации OpenAPI
@app.route('/static/<path:path>')
def send_spec(path):
    return send_from_directory('static', path)

# Модель для таблицы 'categories'
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}

# Модель для таблицы 'bikes'
class Bike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('bikes', lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "stock": self.stock,
            "category": self.category.name
        }

# Инициализация базы данных
with app.app_context():
    db.create_all()

# Эндпоинт для получения всех категорий
@app.route('/categories', methods=['GET'])
def get_categories():
    categories = Category.query.all()
    return jsonify([c.to_dict() for c in categories])

# Эндпоинт для добавления новой категории
@app.route('/categories', methods=['POST'])
def create_category():
    data = request.json
    new_category = Category(name=data['name'])
    db.session.add(new_category)
    db.session.commit()
    return jsonify(new_category.to_dict()), 201

# Эндпоинт для получения информации о конкретной категории
@app.route('/categories/<int:category_id>', methods=['GET'])
def get_category(category_id):
    category = Category.query.get_or_404(category_id)
    return jsonify(category.to_dict())

# Эндпоинт для обновления информации о категории
@app.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    data = request.json
    category = Category.query.get_or_404(category_id)
    
    category.name = data.get('name', category.name)

    db.session.commit()
    return jsonify(category.to_dict())

# Эндпоинт для удаления категории
@app.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return '', 204

# Эндпоинт для получения всех велосипедов
@app.route('/bikes', methods=['GET'])
def get_bikes():
    bikes = Bike.query.all()
    return jsonify([b.to_dict() for b in bikes])

# Эндпоинт для добавления нового велосипеда
@app.route('/bikes', methods=['POST'])
def create_bike():
    data = request.json
    category = Category.query.get_or_404(data['category_id'])
    new_bike = Bike(
        name=data['name'],
        price=data['price'],
        stock=data['stock'],
        category_id=category.id
    )
    db.session.add(new_bike)
    db.session.commit()
    return jsonify(new_bike.to_dict()), 201

# Эндпоинт для получения информации о конкретном велосипеде
@app.route('/bikes/<int:bike_id>', methods=['GET'])
def get_bike(bike_id):
    bike = Bike.query.get_or_404(bike_id)
    return jsonify(bike.to_dict())

# Эндпоинт для обновления информации о велосипеде
@app.route('/bikes/<int:bike_id>', methods=['PUT'])
def update_bike(bike_id):
    data = request.json
    bike = Bike.query.get_or_404(bike_id)
    
    bike.name = data.get('name', bike.name)
    bike.price = data.get('price', bike.price)
    bike.stock = data.get('stock', bike.stock)
    
    if 'category_id' in data:
        category = Category.query.get_or_404(data['category_id'])
        bike.category_id = category.id

    db.session.commit()
    return jsonify(bike.to_dict())

# Эндпоинт для удаления велосипеда
@app.route('/bikes/<int:bike_id>', methods=['DELETE'])
def delete_bike(bike_id):
    bike = Bike.query.get_or_404(bike_id)
    db.session.delete(bike)
    db.session.commit()
    return '', 204

if __name__ == '__main__':
    app.run(debug=True)