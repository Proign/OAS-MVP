from flask import Flask, jsonify, request, redirect, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
from prometheus_client import generate_latest, Histogram, Counter
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
import os
import time
import logging


# Инициализация приложения Flask
app = Flask(__name__)


# Настройки базы данных SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
    os.path.join(basedir, 'bikeshop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("bikeshop")


# Настройка метрик Prometheus
request_count = Counter('bikeshop_requests_total', 'Total number of requests')
request_latency = Histogram('bikeshop_request_latency_seconds', 'Request latency in seconds')
response_size = Histogram('bikeshop_response_size_bytes', 'Response size in bytes')


@app.route('/metrics')
def metrics_endpoint():
    return generate_latest(), 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}


# Swagger UI
SWAGGER_URL = '/swagger'
API_URL = '/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL, API_URL, config={'app_name': "Bike Shop API"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)


@app.route('/')
def index():
    return redirect('/swagger')


@app.route('/static/<path:path>')
def send_spec(path):
    return send_from_directory('static', path)


# OpenTelemetry: настройка трейсинга
resource = Resource(attributes={"service.name": "bikeshop"})
trace_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(trace_provider)

otlp_exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318/v1/traces",
    headers={}
)
span_processor = BatchSpanProcessor(otlp_exporter)
trace_provider.add_span_processor(span_processor)

tracer = trace.get_tracer(__name__)


# Инструментирование Flask и SQLAlchemy
FlaskInstrumentor().instrument_app(app)

with app.app_context():  # Устанавливаем контекст приложения
    SQLAlchemyInstrumentor().instrument(engine=db.engine)


# Модели базы данных
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


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


# Обертка для измерения времени выполнения
def time_request(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        with tracer.start_as_current_span(func.__name__):
            result = func(*args, **kwargs)
        latency = time.time() - start_time

        # Логирование метрик
        request_latency.observe(latency)
        response_size.observe(len(result.data) if hasattr(result, 'data') else 0)
        request_count.inc()
        logger.info(f"Endpoint {func.__name__} executed in {latency:.2f} seconds.")
        return result
    wrapper.__name__ = func.__name__
    return wrapper


# CRUD для категорий
@app.route('/categories', methods=['GET'])
@time_request
def get_categories():
    categories = Category.query.all()
    logger.info("Fetched all categories.")
    return jsonify([c.to_dict() for c in categories])


@app.route('/categories', methods=['POST'])
@time_request
def create_category():
    data = request.json
    new_category = Category(name=data['name'])
    db.session.add(new_category)
    db.session.commit()
    logger.info(f"Category created: {new_category.name}")
    return jsonify(new_category.to_dict()), 201


@app.route('/categories/<int:category_id>', methods=['GET'])
@time_request
def get_category(category_id):
    category = Category.query.get_or_404(category_id)
    logger.info(f"Fetched category: {category.name}")
    return jsonify(category.to_dict())


@app.route('/categories/<int:category_id>', methods=['PUT'])
@time_request
def update_category(category_id):
    data = request.json
    category = Category.query.get_or_404(category_id)
    category.name = data.get('name', category.name)
    db.session.commit()
    logger.info(f"Updated category {category_id}: {category.name}")
    return jsonify(category.to_dict())


@app.route('/categories/<int:category_id>', methods=['DELETE'])
@time_request
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    logger.info(f"Deleted category {category_id}.")
    return '', 204


# CRUD для велосипедов
@app.route('/bikes', methods=['GET'])
@time_request
def get_bikes():
    bikes = Bike.query.all()
    logger.info("Fetched all bikes.")
    return jsonify([b.to_dict() for b in bikes])


@app.route('/bikes', methods=['POST'])
@time_request
def create_bike():
    data = request.json
    category = Category.query.get_or_404(data['category_id'])
    new_bike = Bike(name=data['name'], 
                    price=data['price'], 
                    stock=data['stock'], 
                    category_id=category.id)
    db.session.add(new_bike)
    db.session.commit()
    logger.info(f"Bike created: {new_bike.name}")
    return jsonify(new_bike.to_dict()), 201


@app.route('/bikes/<int:bike_id>', methods=['GET'])
@time_request
def get_bike(bike_id):
    bike = Bike.query.get_or_404(bike_id)
    logger.info(f"Fetched bike: {bike.name}")
    return jsonify(bike.to_dict())


@app.route('/bikes/<int:bike_id>', methods=['PUT'])
@time_request
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
    logger.info(f"Updated bike {bike_id}: {bike.name}")
    return jsonify(bike.to_dict())


@app.route('/bikes/<int:bike_id>', methods=['DELETE'])
@time_request
def delete_bike(bike_id):
    bike = Bike.query.get_or_404(bike_id)
    db.session.delete(bike)
    db.session.commit()
    logger.info(f"Deleted bike {bike_id}.")
    return '', 204


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
