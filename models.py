from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property

db = SQLAlchemy()

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    has_size = db.Column(db.Boolean, default=False)
    has_power = db.Column(db.Boolean, default=False)
    has_model = db.Column(db.Boolean, default=False)
    custom_fields = db.Column(db.Text)  # comma-separated field names

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    brand = db.Column(db.String(50))
    state = db.Column(db.String(20), default='stock')  # stock, loan, broken
    location = db.Column(db.String(20), default='club')  # club, loan
    comments = db.Column(db.Text)
    # specific fields
    size = db.Column(db.String(20))
    power = db.Column(db.String(20))
    model = db.Column(db.String(50))
    custom_values = db.Column(db.JSON)
    category = db.relationship('Category', backref='products')

composite_components = db.Table('composite_components',
    db.Column('composite_id', db.Integer, db.ForeignKey('composite_product.id')),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'))
)

class CompositeProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(10))  # BB, CL
    status = db.Column(db.String(20), default='club')  # club, loan
    components = db.relationship('Product', secondary=composite_components, backref='composites')

class Archer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    license_number = db.Column(db.String(20), unique=True, nullable=False)
    # Archer-specific fields
    bow_length = db.Column(db.String(50))
    draw_length = db.Column(db.String(50))
    bow_type = db.Column(db.String(50))
    notes = db.Column(db.Text)

    @hybrid_property
    def name(self):
        if self.first_name:
            return f"{self.first_name} {self.last_name}"
        return self.last_name

    @property
    def current_assignment(self):
        """Get the current (non-returned) bow assignment for this archer"""
        return Assignment.query.filter_by(archer_id=self.id, date_returned=None).first()

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    archer_id = db.Column(db.Integer, db.ForeignKey('archer.id'), nullable=False)
    composite_id = db.Column(db.Integer, db.ForeignKey('composite_product.id'), nullable=False)
    date_assigned = db.Column(db.DateTime, default=db.func.now())
    date_returned = db.Column(db.DateTime, nullable=True)
    archer = db.relationship('Archer', backref='assignments')
    composite = db.relationship('CompositeProduct', backref='assignments')

class HistoryEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

archer_courses = db.Table('archer_courses',
    db.Column('archer_id', db.Integer, db.ForeignKey('archer.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM format
    end_time = db.Column(db.String(5), nullable=False)  # HH:MM format
    level = db.Column(db.String(50), nullable=True)  # débutant, intermédiaire, avancé
    max_archers = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    archers = db.relationship('Archer', secondary=archer_courses, backref='courses')

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    archer_id = db.Column(db.Integer, db.ForeignKey('archer.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=db.func.now())
    archer = db.relationship('Archer', backref='attendances')
    course = db.relationship('Course', backref='attendances')