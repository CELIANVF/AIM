from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config
from models import db, Category, Product, CompositeProduct, Archer, Assignment, HistoryEvent, Course, Attendance
from datetime import datetime, date, timedelta
from dateutil import parser as date_parser
import csv
from io import StringIO

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)

def log_history(event_type, entity_type, entity_id, summary, details=None):
    event = HistoryEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details
    )
    db.session.add(event)
    return event

def seed_categories():
    default_categories = {
        'viseur': {'has_size': False, 'has_power': False, 'has_model': True, 'has_brand': True},
        'stab': {'has_size': False, 'has_power': False, 'has_model': True, 'has_brand': True}
    }
    with app.app_context():
        for cat_name, attrs in default_categories.items():
            cat = Category.query.filter_by(name=cat_name).first()
            if not cat:
                cat = Category(name=cat_name, **attrs)
                db.session.add(cat)
            else:
                # update if not set
                if cat.has_size is None:
                    cat.has_size = attrs['has_size']
                if cat.has_power is None:
                    cat.has_power = attrs['has_power']
                if cat.has_model is None:
                    cat.has_model = attrs['has_model']
                if cat.has_brand is None:
                    cat.has_brand = attrs['has_brand']
        db.session.commit()

@app.route('/')
def index():
    seed_categories()
    products_count = Product.query.count()
    archers_count = Archer.query.count()
    composites_count = CompositeProduct.query.count()
    categories_count = Category.query.count()
    return render_template('index.html', 
                         products_count=products_count,
                         archers_count=archers_count,
                         composites_count=composites_count,
                         categories_count=categories_count)

@app.route('/categories')
def categories():
    cats = Category.query.all()
    return render_template('categories.html', categories=cats)

@app.route('/add_category', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        name = request.form['name']
        has_size = 'has_size' in request.form
        has_power = 'has_power' in request.form
        has_model = 'has_model' in request.form
        has_brand = 'has_brand' in request.form
        custom_fields = request.form.get('custom_fields', '').strip()
        cat = Category(name=name, has_size=has_size, has_power=has_power, has_model=has_model, has_brand=has_brand, custom_fields=custom_fields)
        db.session.add(cat)
        db.session.commit()
        return redirect(url_for('categories'))
    return render_template('add_category.html')

@app.route('/edit_category/<int:cat_id>', methods=['GET', 'POST'])
def edit_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if request.method == 'POST':
        cat.name = request.form['name']
        cat.has_size = 'has_size' in request.form
        cat.has_power = 'has_power' in request.form
        cat.has_model = 'has_model' in request.form
        cat.has_brand = 'has_brand' in request.form
        cat.custom_fields = request.form.get('custom_fields', '').strip()
        db.session.commit()
        return redirect(url_for('categories'))
    return render_template('edit_category.html', category=cat)

@app.route('/delete_category/<int:cat_id>', methods=['POST'])
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    products = Product.query.filter_by(category_id=cat_id).all()
    for prod in products:
        for comp in prod.composites:
            comp.components.remove(prod)
        db.session.delete(prod)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for('categories'))

@app.route('/products')
def products():
    prods = Product.query.join(Category).order_by(Category.name, Product.brand).all()
    return render_template('products.html', products=prods)

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        cat_id = request.form.get('category_id')
        brand = request.form.get('brand', '')
        state = request.form.get('state', 'stock')
        location = request.form.get('location', 'club')
        comments = request.form.get('comments', '')
        size = request.form.get('size')
        power = request.form.get('power')
        model = request.form.get('model')
        # Collect custom fields
        custom_values = {}
        for key, value in request.form.items():
            if key.startswith('custom_'):
                field_name = key[7:].replace('_', ' ')  # remove 'custom_' and replace _ with space
                custom_values[field_name] = value
        prod = Product(category_id=cat_id, brand=brand, state=state, location=location, comments=comments, size=size, power=power, model=model, custom_values=custom_values if custom_values else None)
        db.session.add(prod)
        db.session.commit()
        category = Category.query.get(cat_id)
        log_history(
            event_type='product_created',
            entity_type='product',
            entity_id=prod.id,
            summary=f"Produit créé: {brand} ({category.name if category else 'Catégorie inconnue'})",
            details={
                'category': category.name if category else None,
                'brand': brand,
                'state': state,
                'location': location,
                'size': size,
                'power': power,
                'model': model
            }
        )
        db.session.commit()
        return redirect(url_for('products'))
    cats = Category.query.all()
    return render_template('add_product.html', categories=cats)

@app.route('/edit_product/<int:prod_id>', methods=['GET', 'POST'])
def edit_product(prod_id):
    prod = Product.query.get_or_404(prod_id)
    if request.method == 'POST':
        old_category = prod.category.name if prod.category else None
        old_data = {
            'Catégorie': old_category,
            'Marque': prod.brand,
            'État': prod.state,
            'Lieu': prod.location,
            'Taille': prod.size,
            'Puissance': prod.power,
            'Modèle': prod.model,
            'Commentaires': prod.comments
        }
        prod.category_id = request.form.get('category_id')
        prod.brand = request.form.get('brand', '')
        prod.state = request.form.get('state', 'stock')
        prod.location = request.form.get('location', 'club')
        prod.comments = request.form.get('comments', '')
        prod.size = request.form.get('size')
        prod.power = request.form.get('power')
        prod.model = request.form.get('model')
        # Collect custom fields
        custom_values = {}
        for key, value in request.form.items():
            if key.startswith('custom_'):
                field_name = key[7:].replace('_', ' ')  # remove 'custom_' and replace _ with space
                custom_values[field_name] = value
        prod.custom_values = custom_values if custom_values else None
        new_category = Category.query.get(prod.category_id)
        new_data = {
            'Catégorie': new_category.name if new_category else None,
            'Marque': prod.brand,
            'État': prod.state,
            'Lieu': prod.location,
            'Taille': prod.size,
            'Puissance': prod.power,
            'Modèle': prod.model,
            'Commentaires': prod.comments
        }
        changes = {}
        for key in old_data:
            if old_data.get(key) != new_data.get(key):
                changes[key] = {'from': old_data.get(key), 'to': new_data.get(key)}
        if changes:
            log_history(
                event_type='product_updated',
                entity_type='product',
                entity_id=prod.id,
                summary=f"Produit modifié: {prod.brand} ({new_data.get('Catégorie')})",
                details={'changes': changes}
            )
        db.session.commit()
        return redirect(url_for('products'))
    cats = Category.query.all()
    return render_template('edit_product.html', product=prod, categories=cats)

@app.route('/duplicate_product/<int:prod_id>')
def duplicate_product(prod_id):
    original = Product.query.get_or_404(prod_id)
    # Create a new product with the same attributes
    new_prod = Product(
        category_id=original.category_id,
        brand=original.brand,
        state=original.state,
        location=original.location,
        comments=original.comments,
        size=original.size,
        power=original.power,
        model=original.model,
        custom_values=original.custom_values
    )
    db.session.add(new_prod)
    db.session.commit()
    return redirect(url_for('products'))

@app.route('/composites')
def composites():
    comps = CompositeProduct.query.all()
    return render_template('composites.html', composites=comps)

@app.route('/add_composite', methods=['GET', 'POST'])
def add_composite():
    if request.method == 'POST':
        name = request.form['name']
        type = request.form['type']
        status = request.form['status']
        comp = CompositeProduct(name=name, type=type, status=status)
        db.session.add(comp)
        db.session.commit()
        # add components
        comp_ids = request.form.getlist('components')
        for cid in comp_ids:
            prod = Product.query.get(int(cid))
            if prod:
                comp.components.append(prod)
        components = [f"{p.brand} ({p.category.name})" for p in comp.components]
        log_history(
            event_type='composite_created',
            entity_type='composite',
            entity_id=comp.id,
            summary=f"Arc créé: {comp.name}",
            details={'components': components, 'type': comp.type, 'status': comp.status}
        )
        db.session.commit()
        return redirect(url_for('composites'))
    # pass categories so template can group products by category
    cats = Category.query.order_by(Category.name).all()
    return render_template('add_composite.html', categories=cats)

@app.route('/edit_composite/<int:comp_id>', methods=['GET', 'POST'])
def edit_composite(comp_id):
    comp = CompositeProduct.query.get_or_404(comp_id)
    if request.method == 'POST':
        old_components = [f"{p.brand} ({p.category.name})" for p in comp.components]
        comp.name = request.form['name']
        comp.type = request.form['type']
        comp.status = request.form['status']
        # clear existing components
        comp.components.clear()
        # add new components
        comp_ids = request.form.getlist('components')
        for cid in comp_ids:
            prod = Product.query.get(int(cid))
            if prod:
                comp.components.append(prod)
        new_components = [f"{p.brand} ({p.category.name})" for p in comp.components]
        if old_components != new_components:
            log_history(
                event_type='composite_change',
                entity_type='composite',
                entity_id=comp.id,
                summary=f"Composition modifiée: {comp.name}",
                details={'before': old_components, 'after': new_components}
            )
        db.session.commit()
        return redirect(url_for('composites'))
    prods = Product.query.all()
    return render_template('edit_composite.html', composite=comp, products=prods)

@app.route('/archers')
def archers():
    archs = Archer.query.all()
    return render_template('archers.html', archers=archs)

@app.route('/add_archer', methods=['GET', 'POST'])
def add_archer():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        license = request.form.get('license')
        age = request.form.get('age') or None
        bow_length = request.form.get('bow_length')
        draw_length = request.form.get('draw_length')
        bow_type = request.form.get('bow_type')
        notes = request.form.get('notes')
        arch = Archer(first_name=first_name, last_name=last_name, age=int(age) if age else None, license_number=license, bow_length=bow_length, draw_length=draw_length, bow_type=bow_type, notes=notes)
        db.session.add(arch)
        db.session.commit()
        return redirect(url_for('archers'))
    return render_template('add_archer.html')


@app.route('/edit_archer/<int:archer_id>', methods=['GET', 'POST'])
def edit_archer(archer_id):
    arch = Archer.query.get_or_404(archer_id)
    if request.method == 'POST':
        arch.first_name = request.form.get('first_name')
        arch.last_name = request.form.get('last_name')
        arch.license_number = request.form.get('license')
        age = request.form.get('age') or None
        arch.age = int(age) if age else None
        arch.bow_length = request.form.get('bow_length')
        arch.draw_length = request.form.get('draw_length')
        arch.bow_type = request.form.get('bow_type')
        arch.notes = request.form.get('notes')
        db.session.commit()
        return redirect(url_for('archers'))
    return render_template('edit_archer.html', archer=arch)

@app.route('/assignments')
def assignments():
    assigns = Assignment.query.filter_by(date_returned=None).all()
    return render_template('assignments.html', assignments=assigns)

@app.route('/return/<int:assign_id>', methods=['POST'])
def return_assignment(assign_id):
    assign = Assignment.query.get_or_404(assign_id)
    assign.date_returned = db.func.now()
    assign.composite.status = 'club'
    log_history(
        event_type='assignment_return',
        entity_type='assignment',
        entity_id=assign.id,
        summary=f"Retour: {assign.archer.name} → {assign.composite.name}",
        details={'archer': assign.archer.name, 'composite': assign.composite.name}
    )
    db.session.commit()
    return redirect(url_for('assignments'))

@app.route('/delete_archer/<int:archer_id>', methods=['POST'])
def delete_archer(archer_id):
    arch = Archer.query.get_or_404(archer_id)
    # Delete associated assignments
    Assignment.query.filter_by(archer_id=archer_id).delete()
    db.session.delete(arch)
    db.session.commit()
    return redirect(url_for('archers'))

@app.route('/delete_product/<int:prod_id>', methods=['POST'])
def delete_product(prod_id):
    prod = Product.query.get_or_404(prod_id)
    # Remove from any composites
    for comp in prod.composites:
        comp.components.remove(prod)
    log_history(
        event_type='product_deleted',
        entity_type='product',
        entity_id=prod.id,
        summary=f"Produit supprimé: {prod.brand} ({prod.category.name})",
        details={'category': prod.category.name if prod.category else None, 'brand': prod.brand}
    )
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('products'))

@app.route('/delete_composite/<int:comp_id>', methods=['POST'])
def delete_composite(comp_id):
    comp = CompositeProduct.query.get_or_404(comp_id)
    # Delete associated assignments
    Assignment.query.filter_by(composite_id=comp_id).delete()
    # Clear components
    comp.components.clear()
    log_history(
        event_type='composite_deleted',
        entity_type='composite',
        entity_id=comp.id,
        summary=f"Arc supprimé: {comp.name}",
        details={'type': comp.type, 'status': comp.status}
    )
    db.session.delete(comp)
    db.session.commit()
    return redirect(url_for('composites'))

@app.route('/assign', methods=['GET', 'POST'])
def assign():
    if request.method == 'POST':
        archer_id = request.form['archer_id']
        composite_id = request.form['composite_id']
        assign_obj = Assignment(archer_id=archer_id, composite_id=composite_id)
        db.session.add(assign_obj)
        comp = CompositeProduct.query.get(composite_id)
        comp.status = 'loan'
        archer = Archer.query.get(archer_id)
        log_history(
            event_type='assignment',
            entity_type='assignment',
            entity_id=None,
            summary=f"Assigné: {archer.name if archer else 'Archer inconnu'} ← {comp.name if comp else 'Arc inconnu'}",
            details={'archer': archer.name if archer else None, 'composite': comp.name if comp else None}
        )
        db.session.commit()
        return redirect(url_for('assignments'))
    archer_id = request.args.get('archer_id')
    archs = Archer.query.all()
    comps = CompositeProduct.query.filter_by(status='club').all()
    all_comps = CompositeProduct.query.all()
    selected_archer = Archer.query.get(archer_id) if archer_id else None
    return render_template('assign.html', archers=archs, composites=comps, selected_archer=selected_archer, all_composites=all_comps)

@app.route('/reset_composite_status/<int:comp_id>', methods=['POST'])
def reset_composite_status(comp_id):
    comp = CompositeProduct.query.get_or_404(comp_id)
    comp.status = 'club'
    db.session.commit()
    return redirect(url_for('assign'))

@app.route('/history')
def history():
    events = HistoryEvent.query.order_by(HistoryEvent.created_at.desc()).all()
    assignment_events = [e for e in events if e.event_type in ('assignment', 'assignment_return')]
    composite_events = [e for e in events if e.event_type in ('composite_created', 'composite_change', 'composite_deleted')]
    product_events = [e for e in events if e.event_type in ('product_created', 'product_updated', 'product_deleted')]
    return render_template(
        'history.html',
        assignment_events=assignment_events,
        composite_events=composite_events,
        product_events=product_events
    )

@app.route('/courses')
def courses():
    days_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    courses_list = Course.query.filter_by(active=True).order_by(Course.day_of_week, Course.start_time).all()
    return render_template('courses.html', courses=courses_list, days_names=days_names)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    days_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    if request.method == 'POST':
        name = request.form.get('name', '')
        day_of_week = int(request.form.get('day_of_week', 0))
        start_time = request.form.get('start_time', '')
        end_time = request.form.get('end_time', '')
        level = request.form.get('level', '')
        max_archers = request.form.get('max_archers') or None
        if max_archers:
            max_archers = int(max_archers)
        notes = request.form.get('notes', '')
        
        course = Course(
            name=name,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            level=level,
            max_archers=max_archers,
            notes=notes,
            active=True
        )
        db.session.add(course)
        db.session.commit()
        log_history(
            event_type='course_created',
            entity_type='course',
            entity_id=course.id,
            summary=f"Cours créé: {name} - {days_names[day_of_week]} {start_time}-{end_time}",
            details={'level': level, 'max_archers': max_archers}
        )
        db.session.commit()
        return redirect(url_for('courses'))
    return render_template('add_course.html', days_names=days_names)

@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    days_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    if request.method == 'POST':
        course.name = request.form.get('name', '')
        course.day_of_week = int(request.form.get('day_of_week', 0))
        course.start_time = request.form.get('start_time', '')
        course.end_time = request.form.get('end_time', '')
        course.level = request.form.get('level', '')
        max_archers = request.form.get('max_archers') or None
        course.max_archers = int(max_archers) if max_archers else None
        course.notes = request.form.get('notes', '')
        db.session.commit()
        return redirect(url_for('courses'))
    return render_template('edit_course.html', course=course, days_names=days_names)

@app.route('/delete_course/<int:course_id>', methods=['POST'])
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    # Soft delete by marking as inactive
    course.active = False
    Attendance.query.filter_by(course_id=course_id).delete()
    db.session.commit()
    return redirect(url_for('courses'))

@app.route('/course/<int:course_id>/archers')
def course_archers(course_id):
    course = Course.query.get_or_404(course_id)
    all_archers = Archer.query.all()
    return render_template('course_archers.html', course=course, all_archers=all_archers)

@app.route('/course/<int:course_id>/add_archer/<int:archer_id>', methods=['POST'])
def add_archer_to_course(course_id, archer_id):
    course = Course.query.get_or_404(course_id)
    archer = Archer.query.get_or_404(archer_id)
    if archer not in course.archers:
        course.archers.append(archer)
        db.session.commit()
        log_history(
            event_type='archer_added_to_course',
            entity_type='course',
            entity_id=course_id,
            summary=f"{archer.name} ajouté au cours {course.name}",
            details={'archer': archer.name, 'course': course.name}
        )
        db.session.commit()
    return redirect(url_for('course_archers', course_id=course_id))

@app.route('/course/<int:course_id>/remove_archer/<int:archer_id>', methods=['POST'])
def remove_archer_from_course(course_id, archer_id):
    course = Course.query.get_or_404(course_id)
    archer = Archer.query.get_or_404(archer_id)
    if archer in course.archers:
        course.archers.remove(archer)
        db.session.commit()
    return redirect(url_for('course_archers', course_id=course_id))

@app.route('/course/<int:course_id>/attendance')
def course_attendance(course_id):
    course = Course.query.get_or_404(course_id)
    today = date.today()
    # Get the next 30 days
    end_date = today + timedelta(days=30)
    # Get attendance records for the next 30 days
    attendance_records = Attendance.query.filter(
        Attendance.course_id == course_id,
        Attendance.date >= today,
        Attendance.date <= end_date
    ).order_by(Attendance.date.desc()).all()
    return render_template('course_attendance.html', course=course, attendance_records=attendance_records, today=today)

@app.route('/course/<int:course_id>/mark_attendance', methods=['POST'])
def mark_attendance(course_id):
    course = Course.query.get_or_404(course_id)
    attendance_date = request.form.get('date')
    date_obj = datetime.strptime(attendance_date, '%Y-%m-%d').date()
    
    # Mark all archers in the course
    for archer in course.archers:
        present = f'archer_{archer.id}' in request.form
        # Check if attendance record already exists
        attendance = Attendance.query.filter_by(
            archer_id=archer.id,
            course_id=course_id,
            date=date_obj
        ).first()
        if attendance:
            attendance.present = present
        else:
            attendance = Attendance(
                archer_id=archer.id,
                course_id=course_id,
                date=date_obj,
                present=present
            )
            db.session.add(attendance)
    
    db.session.commit()
    return redirect(url_for('course_attendance', course_id=course_id))

@app.route('/export_products')
def export_products():
    from reportlab.pdfgen import canvas
    from io import BytesIO
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    prods = Product.query.all()
    p.drawString(100, 800, "Liste des produits")
    y = 780
    for prod in prods:
        p.drawString(100, y, f"{prod.id}: {prod.brand} - {prod.category.name} - Etat: {prod.state}")
        y -= 20
        if y < 50:
            p.showPage()
            y = 800
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='products.pdf', mimetype='application/pdf')

@app.route('/export_assignments')
def export_assignments():
    from reportlab.pdfgen import canvas
    from io import BytesIO
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    assigns = Assignment.query.filter_by(date_returned=None).all()
    p.drawString(100, 800, "Assignations actuelles")
    y = 780
    for ass in assigns:
        p.drawString(100, y, f"{ass.archer.name} - {ass.composite.name} - {ass.date_assigned.strftime('%d/%m/%Y')}")
        y -= 20
        if y < 50:
            p.showPage()
            y = 800
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='assignments.pdf', mimetype='application/pdf')

@app.route('/export_composites')
def export_composites():
    from reportlab.pdfgen import canvas
    from io import BytesIO
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    comps = CompositeProduct.query.all()
    p.drawString(100, 800, "Liste des arcs")
    y = 780
    for c in comps:
        p.drawString(100, y, f"{c.name} - Type: {c.type} - Statut: {c.status}")
        y -= 20
        for comp in c.components:
            p.drawString(120, y, f"- {comp.brand} ({comp.category.name})")
            y -= 15
        y -= 5
        if y < 50:
            p.showPage()
            y = 800
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='composites.pdf', mimetype='application/pdf')

@app.route('/import_archers', methods=['GET', 'POST'])
def import_archers():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            try:
                # Lire le fichier avec gestion des guillemets et BOM
                content = file.stream.read().decode("UTF-8-sig")  # UTF-8-sig supprime le BOM
                stream = StringIO(content, newline=None)
                csv_reader = csv.DictReader(stream, delimiter=';', quotechar='"')
                
                imported = 0
                errors = []
                
                # Afficher les fieldnames pour debug
                fieldnames = csv_reader.fieldnames
                if not fieldnames:
                    return render_template('import_archers.html', 
                                         error="Le fichier CSV est vide ou mal formaté")
                
                # Fonction pour nettoyer les clés
                def clean_key(key):
                    if key is None:
                        return None
                    return key.strip().strip('"').strip()
                
                # Créer un mapping des colonnes nettoyées
                clean_fieldnames = {clean_key(f): f for f in fieldnames if f}
                
                # Fonction pour trouver la colonne correspondante
                def find_column(row_dict, *possible_names):
                    for name in possible_names:
                        clean_name = clean_key(name)
                        # Chercher dans les fieldnames nettoyées
                        if clean_name in clean_fieldnames:
                            original_field = clean_fieldnames[clean_name]
                            value = row_dict.get(original_field, '')
                            return value.strip() if isinstance(value, str) else ''
                        # Chercher directement dans la ligne
                        for key, value in row_dict.items():
                            if clean_key(key) == clean_name:
                                return value.strip() if isinstance(value, str) else ''
                    # Si rien n'est trouvé, chercher la première colonne (qui peut être le code)
                    if len(row_dict) > 0:
                        first_value = list(row_dict.values())[0]
                        return first_value.strip() if isinstance(first_value, str) else ''
                    return ''
                
                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        license_number = find_column(row, 'Code adhérent').strip()
                        first_name = find_column(row, 'Prénom').strip()
                        last_name = find_column(row, 'Nom').strip()
                        dob_str = find_column(row, 'DDN').strip()
                        
                        if not license_number or not last_name:
                            errors.append(f"Ligne {row_num}: Code adhérent et Nom sont obligatoires (reçu: code='{license_number}', nom='{last_name}')")
                            continue
                        
                        # Vérifier si l'archer existe déjà
                        existing = Archer.query.filter_by(license_number=license_number).first()
                        if existing:
                            errors.append(f"Ligne {row_num}: L'archer avec le code '{license_number}' existe déjà")
                            continue
                        
                        # Calculer l'âge à partir de la date de naissance
                        age = None
                        if dob_str:
                            try:
                                dob = date_parser.parse(dob_str, dayfirst=True).date()
                                today = date.today()
                                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                            except:
                                pass  # Si la date n'est pas valide, on la ignore
                        
                        archer = Archer(
                            first_name=first_name,
                            last_name=last_name,
                            license_number=license_number,
                            age=age
                        )
                        db.session.add(archer)
                        imported += 1
                    except Exception as e:
                        errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                
                db.session.commit()
                return render_template('import_archers.html', 
                                     success=True,
                                     imported=imported,
                                     errors=errors)
            except Exception as e:
                return render_template('import_archers.html', 
                                     error=f"Erreur lors de la lecture du fichier: {str(e)}")
    
    return render_template('import_archers.html')

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')