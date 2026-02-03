from app import app, db, Archer

with app.app_context():
    archers = Archer.query.all()
    print(f'Found {len(archers)} archers')
    for a in archers:
        print(f'ID: {a.id}, first: {repr(a.first_name)}, last: {repr(a.last_name)}, license: {repr(a.license_number)}')

        # Fix any archers with None last_name
        if a.last_name is None:
            print(f'Fixing archer {a.id} - setting last_name to empty string')
            a.last_name = ''
            db.session.commit()