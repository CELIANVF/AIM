"""Données de démonstration pour une instance AIM neuve."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from models import (
    Archer,
    Assignment,
    Attendance,
    Category,
    CompositeProduct,
    Course,
    InscriptionEvent,
    InscriptionEventRegistration,
    Product,
    db,
)


def _already_seeded() -> bool:
    return Category.query.count() > 0


def seed_demo_data(club_name: str | None = None) -> dict[str, int]:
    """Peuple la base avec des données réalistes pour tester AIM."""
    if _already_seeded():
        return {'skipped': 1}

    club = (club_name or 'Club de tir à l\'arc').strip() or 'Club de tir à l\'arc'

    categories = [
        Category(
            name='Poignée',
            position=1,
            has_brand=True,
            has_model=True,
        ),
        Category(
            name='Branchages',
            position=2,
            has_brand=True,
            has_model=True,
        ),
        Category(
            name='Flèches',
            position=3,
            has_brand=True,
            has_model=False,
            custom_fields='spine,longueur',
            field_units={'spine': '', 'longueur': 'pouces'},
        ),
        Category(
            name='Viseur',
            position=4,
            has_brand=True,
            has_model=True,
        ),
        Category(
            name='Stabilisateur',
            position=5,
            has_brand=True,
            has_model=False,
        ),
    ]
    db.session.add_all(categories)
    db.session.flush()

    cat = {c.name: c for c in categories}

    products = [
        Product(category_id=cat['Poignée'].id, brand='Hoyt', model='Formula Xi', state='stock', location='club', tag='P-001'),
        Product(category_id=cat['Poignée'].id, brand='PSE', model='Supra', state='stock', location='club', tag='P-002'),
        Product(category_id=cat['Branchages'].id, brand='Easton', model='X10', state='stock', location='club', tag='P-003'),
        Product(category_id=cat['Branchages'].id, brand='Carbon Express', model='Maxima', state='stock', location='club', tag='P-004'),
        Product(category_id=cat['Flèches'].id, brand='Easton', state='stock', location='club', tag='P-005',
                custom_values={'spine': '600', 'longueur': '30'}),
        Product(category_id=cat['Flèches'].id, brand='Easton', state='stock', location='club', tag='P-006',
                custom_values={'spine': '500', 'longueur': '28'}),
        Product(category_id=cat['Viseur'].id, brand='Shibuya', model='DX', state='stock', location='club', tag='P-007'),
        Product(category_id=cat['Stabilisateur'].id, brand='Avalon', state='stock', location='club', tag='P-008'),
        Product(category_id=cat['Poignée'].id, brand='Samick', model='Avanza', state='stock', location='club', tag='P-009'),
        Product(category_id=cat['Branchages'].id, brand='SF', model='Premium', state='stock', location='club', tag='P-010'),
    ]
    db.session.add_all(products)
    db.session.flush()

    bows = [
        CompositeProduct(name='Arc club débutant', type='BB', status='club', tag='A-001'),
        CompositeProduct(name='Arc prêt compétition', type='BB', status='loan', tag='A-002'),
    ]
    db.session.add_all(bows)
    db.session.flush()

    bows[0].components.extend([products[0], products[2], products[4], products[6]])
    bows[1].components.extend([products[1], products[3], products[5], products[7]])

    archers = [
        Archer(first_name='Marie', last_name='Dupont', license_number='U25678901', categorie='Senior F',
               bow_type='Classique', email='marie.dupont@exemple.fr'),
        Archer(first_name='Lucas', last_name='Martin', license_number='U25678902', categorie='U18 H',
               bow_type='Poulies', bow_length='68"', draw_length='28"'),
        Archer(first_name='Sophie', last_name='Bernard', license_number='U25678903', categorie='Senior F',
               bow_type='Classique'),
        Archer(first_name='Thomas', last_name='Petit', license_number='U25678904', categorie='U15 H',
               bow_type='Classique'),
        Archer(first_name='Émilie', last_name='Roux', license_number='U25678905', categorie='Senior F',
               bow_type='Poulies'),
        Archer(first_name='Antoine', last_name='Moreau', license_number='U25678906', categorie='U21 H',
               bow_type='Classique'),
    ]
    db.session.add_all(archers)
    db.session.flush()

    courses = [
        Course(name=f'{club} — Débutants', day_of_week=2, start_time='18:00', end_time='20:00',
               level='débutant', max_archers=12, active=True),
        Course(name=f'{club} — Perfectionnement', day_of_week=5, start_time='10:00', end_time='12:00',
               level='intermédiaire', max_archers=10, active=True),
    ]
    db.session.add_all(courses)
    db.session.flush()

    courses[0].archers.extend(archers[:4])
    courses[1].archers.extend(archers[2:])

    today = date.today()
    last_wed = today - timedelta(days=(today.weekday() - 2) % 7 or 7)
    db.session.add(Attendance(archer_id=archers[0].id, course_id=courses[0].id, date=last_wed, present=True))
    db.session.add(Attendance(archer_id=archers[1].id, course_id=courses[0].id, date=last_wed, present=True))
    db.session.add(Attendance(archer_id=archers[2].id, course_id=courses[0].id, date=last_wed, present=False,
                               notes='Absent — voyage'))

    db.session.add(Assignment(
        archer_id=archers[1].id,
        composite_id=bows[1].id,
        date_assigned=datetime.utcnow() - timedelta(days=14),
    ))

    event = InscriptionEvent(
        title='Championnat départemental',
        recipient_name='Ligue IDF',
        lieu='Gymnase municipal — Paris 15e',
        start_date=today + timedelta(days=21),
        end_date=today + timedelta(days=21),
        open_for_archer_registration=True,
        archer_registration_deadline=today + timedelta(days=14),
    )
    db.session.add(event)
    db.session.flush()

    db.session.add(InscriptionEventRegistration(
        event_id=event.id,
        archer_id=archers[0].id,
        discipline='salle',
        age_category='Senior F',
        weapon_choice='Arc classique',
        blason='Tricolore',
        distance_label='18 m',
    ))
    db.session.add(InscriptionEventRegistration(
        event_id=event.id,
        archer_id=archers[1].id,
        discipline='salle',
        age_category='U18 H',
        weapon_choice='Arc à poulies',
        blason='Tricolore',
        distance_label='18 m',
    ))

    db.session.commit()
    return {
        'categories': len(categories),
        'products': len(products),
        'composites': len(bows),
        'archers': len(archers),
        'courses': len(courses),
        'events': 1,
    }
