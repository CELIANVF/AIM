from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index
from sqlalchemy.ext.hybrid import hybrid_property
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='responsable', nullable=False)  # admin, responsable, lecteur, entraineur
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_responsable(self):
        return self.role in ('admin', 'responsable')
    
    def can_delete(self):
        return self.role == 'admin'
    
    def can_edit(self):
        return self.role in ('admin', 'responsable')
    
    def can_view(self):
        return True
    
    def can_create_archer_account(self):
        """Compte de connexion archer (e-mail + mot de passe provisoire) : pas réservé au seul rôle éditeur fiche."""
        return self.role in ('admin', 'responsable', 'entraineur', 'editeur')
    
    # Permissions spécifiques par fonctionnalité
    def can_manage_archers(self):
        return self.role in ('admin', 'responsable', 'editeur')
    
    def can_manage_equipment(self):
        return self.role in ('admin', 'responsable')
    
    def can_view_equipment(self):
        return self.role in ('admin', 'responsable', 'lecteur', 'entraineur')
    
    def can_manage_courses(self):
        return self.role in ('admin', 'responsable')
    
    def can_manage_attendance(self):
        return self.role in ('admin', 'responsable', 'entraineur')
    
    def can_view_courses(self):
        return self.role in ('admin', 'responsable', 'lecteur', 'entraineur')
    
    def can_manage_assignments(self):
        return self.role in ('admin', 'responsable')
    
    def can_manage_assignments_for_coach(self):
        return self.role in ('admin', 'responsable', 'entraineur')
    
    def can_view_assignments(self):
        return self.role in ('admin', 'responsable', 'lecteur', 'entraineur')
    
    def can_view_history(self):
        return self.role in ('admin', 'responsable', 'lecteur', 'entraineur')


class UserLoginEvent(db.Model):
    """Journal des tentatives de connexion (succès et échecs), par utilisateur et IP."""
    __tablename__ = 'user_login_event'
    __table_args__ = (
        Index('ix_user_login_event_user_id_created_at', 'user_id', 'created_at'),
        Index('ix_user_login_event_ip_address_created_at', 'ip_address', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    attempted_username = db.Column(db.String(80), nullable=True)
    success = db.Column(db.Boolean, nullable=False, default=True)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    user = db.relationship('User', backref=db.backref('login_events', lazy='dynamic'))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    name = db.Column(db.String(50), unique=True, nullable=False)
    has_size = db.Column(db.Boolean, default=False)
    has_power = db.Column(db.Boolean, default=False)
    has_model = db.Column(db.Boolean, default=True)
    has_brand = db.Column(db.Boolean, default=True)
    custom_fields = db.Column(db.Text)  # comma-separated field names
    field_units = db.Column(db.JSON)  # mapping field_name -> unit (e.g. {'size':'pouces', 'power':'livres', 'latéralité':'gauche'})

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
    # Code d'identification physique (ex. "P-001") — imprimé sur l'étiquette du matériel
    tag = db.Column(db.String(32), unique=True, index=True, nullable=True)
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
    # Code d'identification physique (ex. "A-001") — imprimé sur l'étiquette de l'arc
    tag = db.Column(db.String(32), unique=True, index=True, nullable=True)
    components = db.relationship('Product', secondary=composite_components, backref='composites')

class Archer(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    license_number = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), nullable=True)
    categorie = db.Column(db.String(50), nullable=True)
    # Archer-specific fields
    bow_length = db.Column(db.String(50))
    draw_length = db.Column(db.String(50))
    bow_type = db.Column(db.String(50))
    notes = db.Column(db.Text)
    # Account credentials (for archers with login access)
    password_hash = db.Column(db.String(255), nullable=True)
    # Relationships with cascade delete
    assignments = db.relationship('Assignment', backref='archer', cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', backref='archer', cascade='all, delete-orphan')

    def get_id(self):
        """Évite collision d'id avec la table user dans la session Flask-Login."""
        return f'archer:{self.id}'

    @property
    def role(self):
        """Profil affichage / menus (pas une colonne SQL)."""
        return 'archer'

    @property
    def username(self):
        """Libellé en-tête : identifiant de connexion = e-mail."""
        return (self.email or '').strip() or (self.name or 'archer')

    def set_password(self, password):
        """Hash and set the password for this archer account."""
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if the provided password matches the stored hash."""
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password) if self.password_hash else False

    @property
    def has_account(self):
        """Check if this archer has a login account."""
        return self.password_hash is not None

    # Droits type « lecteur » (consultation club, sans gestion)
    def is_admin(self):
        return False

    def is_responsable(self):
        return False

    def can_delete(self):
        return False

    def can_edit(self):
        return False

    def can_view(self):
        return True

    def can_create_archer_account(self):
        return False

    def can_manage_archers(self):
        return False

    def can_manage_equipment(self):
        return False

    def can_view_equipment(self):
        return False

    def can_manage_courses(self):
        return False

    def can_manage_attendance(self):
        return False

    def can_view_courses(self):
        return False

    def can_manage_assignments(self):
        return False

    def can_manage_assignments_for_coach(self):
        return False

    def can_view_assignments(self):
        return False

    def can_view_history(self):
        return False

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
    course = db.relationship('Course', backref='attendances')


class InscriptionEvent(db.Model):
    """Événement (concours, départ…) pour lequel on prépare un mail / PDF d'inscription."""
    __tablename__ = 'inscription_event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='Événement')
    recipient_name = db.Column(db.String(120), nullable=True)
    depart_phrase = db.Column(db.String(500), nullable=True)
    depart_phrases_json = db.Column(db.Text, nullable=True)
    lieu = db.Column(db.String(200), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    blasons_line = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    open_for_archer_registration = db.Column(db.Boolean, default=False, nullable=False)
    archer_registration_deadline = db.Column(db.Date, nullable=True)
    # JSON liste de codes discipline (ex. ["salle"]). Vide / NULL = toutes les disciplines.
    allowed_disciplines_json = db.Column(db.Text, nullable=True)

    registrations = db.relationship(
        'InscriptionEventRegistration',
        back_populates='event',
        cascade='all, delete-orphan',
    )


class InscriptionEventRegistration(db.Model):
    """Archer inscrit à un événement d'inscription (discipline, catégorie, arme, blason, distance/pique)."""
    __tablename__ = 'inscription_event_registration'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('inscription_event.id'), nullable=False)
    archer_id = db.Column(db.Integer, db.ForeignKey('archer.id'), nullable=False)
    weapon_choice = db.Column(db.String(80), nullable=True)
    discipline = db.Column(db.String(40), nullable=True)
    age_category = db.Column(db.String(80), nullable=True)
    blason = db.Column(db.String(120), nullable=True)
    distance_label = db.Column(db.String(60), nullable=True)
    pike_label = db.Column(db.String(60), nullable=True)
    depart_index = db.Column(db.Integer, nullable=True)

    event = db.relationship('InscriptionEvent', back_populates='registrations')
    archer = db.relationship('Archer', backref='inscription_event_registrations')

    __table_args__ = (
        db.UniqueConstraint('event_id', 'archer_id', name='uq_inscription_event_archer'),
    )