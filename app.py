from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import (
    db,
    User,
    UserLoginEvent,
    Category,
    Product,
    CompositeProduct,
    Archer,
    Assignment,
    HistoryEvent,
    Course,
    Attendance,
    InscriptionEvent,
    InscriptionEventRegistration,
)
from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from dateutil import parser as date_parser
import csv
import json
import re
import unicodedata
from io import StringIO
from functools import wraps
import click

# Armes proposées pour les textes d'inscription (mail / PDF) — « fiche » = bow_type de l'archer
REGISTRATION_WEAPON_CHOICES = [
    ('__fiche__', 'Comme sur la fiche archer'),
    ('CL', 'Classique (CL)'),
    ('BB', 'Barebow (BB)'),
    ('Compound', ' poulies'),
    ('Longbow', 'Longbow'),
    ('Autre', 'Autre'),
]

# Anciennes valeurs enregistrées (synonymes) → code canonique
REGISTRATION_WEAPON_ALIASES = {
    'Classique': 'CL',
    'Barebow': 'BB',
}

REGISTRATION_WEAPON_LABELS = dict(REGISTRATION_WEAPON_CHOICES)

# Fiche archer : type d'arc (mêmes codes que l'inscription, sans « comme sur la fiche »)
ARCHER_BOW_TYPE_CHOICES = [
    ('CL', 'Classique (CL)'),
    ('BB', 'Barebow (BB)'),
    ('Compound', 'Compound (poulies)'),
    ('Longbow', 'Longbow'),
    ('Autre', 'Autre'),
]
ARCHER_BOW_TYPE_VALID_CODES = frozenset(c[0] for c in ARCHER_BOW_TYPE_CHOICES)


def _canonical_archer_bow_type_code(stored):
    """Associe une valeur en base au code du select ; None si chaîne libre non reconnue."""
    s = (stored or '').strip()
    if not s:
        return None
    s0 = REGISTRATION_WEAPON_ALIASES.get(s, s)
    if s0 in ARCHER_BOW_TYPE_VALID_CODES:
        return s0
    if s0 == 'CO' or str(s0).upper() == 'CO':
        return 'Compound'
    sl = s.lower()
    if s0 in ('LD', 'Longbow') or 'longbow' in sl or 'arc droit' in sl:
        return 'Longbow'
    if 'compound' in sl or 'poulie' in sl or sl == 'co':
        return 'Compound'
    if s0 == 'BB' or 'bare' in sl:
        return 'BB'
    if s0 == 'CL' or sl == 'cl' or ('classique' in sl and 'compound' not in sl):
        return 'CL'
    if s0 == 'Autre' or s == 'Autre':
        return 'Autre'
    return None


def _archer_bow_type_form_value(stored):
    """Valeur à pré-sélectionner : code canonique ou texte brut si non mappé."""
    s = (stored or '').strip()
    if not s:
        return ''
    c = _canonical_archer_bow_type_code(s)
    return c if c is not None else s


def _normalize_archer_bow_type_from_form(raw):
    """Valeur POST → stockage (normalise synonymes, conserve texte libre hérité)."""
    v = (raw or '').strip()
    if not v:
        return None
    c = _canonical_archer_bow_type_code(v)
    return c if c is not None else v


def _normalize_archer_email(raw):
    if raw is None:
        return None
    s = raw.strip() if isinstance(raw, str) else str(raw).strip()
    return s[:255] if s else None


def _registration_weapon_canonical(weapon_choice):
    w = (weapon_choice or '').strip()
    if not w:
        w = '__fiche__'
    if w == '__fiche__':
        return '__fiche__'
    return REGISTRATION_WEAPON_ALIASES.get(w, w)



# (code, libellé affiché, mode distance/pique pour le formulaire et le texte)
INSCRIPTION_DISCIPLINES = [
    ('salle', 'Tir en salle', 'distance'),
    ('exterieur_di', 'Tir en extérieur DI', 'distance'),
    ('exterieur_dn', 'Tir en extérieur DN', 'distance'),
    ('nature', 'Tir nature', 'pike'),
    ('parcours', '3D', 'pike'),
    ('campagne', 'Campagne', 'pike'),
    ('beursault', 'Beursault', 'distance'),
    ('autre', 'Autre', 'both'),
]
DEFAULT_INSCRIPTION_DISCIPLINE = 'salle'

# Anciens codes (inscriptions déjà enregistrées)
INSCRIPTION_DISCIPLINE_ALIASES = {
    'blason_salle': 'salle',
    'blason_ext': 'exterieur_di',
    'field': 'campagne',
}


def _inscription_discipline_canonical(code):
    c = (code or '').strip()
    if not c:
        return DEFAULT_INSCRIPTION_DISCIPLINE
    c = INSCRIPTION_DISCIPLINE_ALIASES.get(c, c)
    valid = {x[0] for x in INSCRIPTION_DISCIPLINES}
    return c if c in valid else DEFAULT_INSCRIPTION_DISCIPLINE

INSCRIPTION_AGE_CATEGORY_CHOICES = [
    ('__fiche__', 'Comme sur la fiche'),
    ('U11', 'U11'),
    ('U13', 'U13'),
    ('U15', 'U15'),
    ('U18', 'U18'),
    ('U21', 'U21'),
    ('S1', 'S1'),
    ('S2', 'S2'),
    ('S3', 'S3'),
    ('__custom__', 'Autre…'),
]

# Beursault : même libellé pour toutes les catégories (aussi une entrée de liste blason).
INSCRIPTION_BEURSAULT_BLASON_LINE = 'Blason Beursault (identique toutes catégories)'

INSCRIPTION_BLASON_CHOICES = [
    ('', '—'),
    ('Ø 40 cm', 'Ø 40 cm (normal)'),
    ('Trispot 40', 'Trispot 40'),
    ('Trispot 60', 'Trispot 60'),
    ('Ø 60 cm', 'Ø 60 cm'),
    ('Ø 80 cm', 'Ø 80 cm'),
    ('Ø 122 cm', 'Ø 122 cm'),
    ('80 cm (1-X)', '80 cm (1-X)'),
    ('80 cm (5-X)', '80 cm (5-X)'),
    (INSCRIPTION_BEURSAULT_BLASON_LINE, INSCRIPTION_BEURSAULT_BLASON_LINE),
]

# Anciennes valeurs enregistrées → codes actuels (liste réduite)
INSCRIPTION_BLASON_ALIASES = {
    'Ø 40 cm ou Trispot': 'Ø 40 cm',
    'Trispot Ø 40': 'Trispot 40',
    'Trispot': 'Trispot 40',
    'Trispot / 3 verticaux': 'Trispot 40',
}


def _inscription_blason_canonical(stored):
    s = (stored or '').strip()
    return INSCRIPTION_BLASON_ALIASES.get(s, s)

# Distance + blason par catégorie d’âge et type d’arc (CL / CO poulies / BB)
# Tuples : (distance, blason) avec blason ∈ INSCRIPTION_BLASON_CHOICES ; None = non régi (ex. CO U11–U15 en DI)
# --- Tir en salle ---
INSCRIPTION_CAT_WEAPON_TARGETS_SALLE = {
    'U11': {
        'CL': ('10 m', 'Ø 80 cm'),
        'CO': ('10 m', 'Ø 80 cm'),
        'BB': ('10 m', 'Ø 80 cm'),
    },
    'U13': {
        'CL': ('18 m', 'Ø 80 cm'),
        'CO': ('18 m', 'Ø 80 cm'),
        'BB': ('18 m', 'Ø 80 cm'),
    },
    'U15': {
        'CL': ('18 m', 'Ø 60 cm'),
        'CO': ('18 m', 'Ø 60 cm'),
        'BB': ('18 m', 'Ø 80 cm'),
    },
    'U18': {
        'CL': ('18 m', 'Ø 40 cm'),
        'CO': ('18 m', 'Trispot 40'),
        'BB': ('18 m', 'Ø 40 cm'),
    },
    'U21_SPLUS': {
        'CL': ('18 m', 'Ø 40 cm'),
        'CO': ('18 m', 'Trispot 40'),
        'BB': ('18 m', 'Ø 40 cm'),
    },
}

# --- Tir en extérieur DI (distances internationales, tableau officiel) ---
INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DI = {
    'U11': {
        'CL': ('20 m', '80 cm (1-X)'),
        'CO': None,
        'BB': ('20 m', '80 cm (1-X)'),
    },
    'U13': {
        'CL': ('30 m', '80 cm (1-X)'),
        'CO': None,
        'BB': ('30 m', '80 cm (1-X)'),
    },
    'U15': {
        'CL': ('40 m', '80 cm (1-X)'),
        'CO': None,
        'BB': ('40 m', '80 cm (1-X)'),
    },
    'U18': {
        'CL': ('60 m', 'Ø 122 cm'),
        'CO': ('50 m', '80 cm (5-X)'),
        'BB': ('60 m', 'Ø 122 cm'),
    },
    'U21_S12': {
        'CL': ('70 m', 'Ø 122 cm'),
        'CO': ('50 m', '80 cm (5-X)'),
        'BB': ('70 m', 'Ø 122 cm'),
    },
    'S3': {
        'CL': ('60 m', 'Ø 122 cm'),
        'CO': ('50 m', '80 cm (5-X)'),
        'BB': ('60 m', 'Ø 122 cm'),
    },
}

# --- Tir en extérieur DN (distances nationales, tableau n°2) ---
INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DN = {
    'U13': {
        'CL': ('20 m', '80 cm (1-X)'),
        'CO': ('30 m', '80 cm (1-X)'),
        'BB': None,
    },
    'U15': {
        'CL': ('30 m', '80 cm (1-X)'),
        'CO': ('30 m', '80 cm (1-X)'),
        'BB': ('30 m', '80 cm (1-X)'),
    },
    'U18': {
        'CL': ('50 m', 'Ø 122 cm'),
        'CO': ('50 m', 'Ø 122 cm'),
        'BB': ('30 m', '80 cm (1-X)'),
    },
    'U21_S12': {
        'CL': ('50 m', 'Ø 122 cm'),
        'CO': ('50 m', 'Ø 122 cm'),
        'BB': ('50 m', 'Ø 122 cm'),
    },
    'S3': {
        'CL': ('50 m', 'Ø 122 cm'),
        'CO': ('50 m', 'Ø 122 cm'),
        'BB': ('50 m', 'Ø 122 cm'),
    },
}

def _inscription_beursault_row(dist):
    t = (dist, INSCRIPTION_BEURSAULT_BLASON_LINE)
    return {'CL': t, 'CO': t, 'BB': t, 'LD': t}


INSCRIPTION_CAT_WEAPON_TARGETS_BEURSAULT = {
    'U13': _inscription_beursault_row('30 m'),
    'U15': _inscription_beursault_row('30 m'),
    'U18': _inscription_beursault_row('50 m'),
    'U21_SPLUS': _inscription_beursault_row('50 m'),
}

INSCRIPTION_TARGET_TABLES_BY_DISCIPLINE = {
    'salle': INSCRIPTION_CAT_WEAPON_TARGETS_SALLE,
    'exterieur_di': INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DI,
    'exterieur_dn': INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DN,
    'beursault': INSCRIPTION_CAT_WEAPON_TARGETS_BEURSAULT,
}

# Tir en Campagne — couleur de piquet (CL, CO, BB, arc droit ; hors arc chasse / poulies sans viseur)
INSCRIPTION_CAMPAGNE_PIQUETS = {
    'U13': {
        'CL': 'Piquet blanc',
        'CO': 'Piquet blanc',
        'BB': None,
        'LD': 'Piquet blanc',
    },
    'U15': {
        'CL': 'Piquet blanc',
        'CO': 'Piquet blanc',
        'BB': 'Piquet blanc',
        'LD': 'Piquet blanc',
    },
    'U18': {
        'CL': 'Piquet bleu',
        'CO': 'Piquet bleu',
        'BB': 'Piquet blanc',
        'LD': 'Piquet blanc',
    },
    'U21_SPLUS': {
        'CL': 'Piquet rouge',
        'CO': 'Piquet rouge',
        'BB': 'Piquet bleu',
        'LD': 'Piquet blanc',
    },
}

# Alias rétrocompat / lectures internes
INSCRIPTION_CAT_WEAPON_TARGETS = INSCRIPTION_CAT_WEAPON_TARGETS_SALLE

INSCRIPTION_DISTANCE_CHOICES = [
    ('', '—'),
    ('6 m', '6 m'),
    ('8 m', '8 m'),
    ('10 m', '10 m'),
    ('12 m', '12 m'),
    ('15 m', '15 m'),
    ('18 m', '18 m'),
    ('20 m', '20 m'),
    ('25 m', '25 m'),
    ('30 m', '30 m'),
    ('40 m', '40 m'),
    ('50 m', '50 m'),
    ('60 m', '60 m'),
    ('70 m', '70 m'),
    ('90 m', '90 m'),
    ('__custom__', 'Autre…'),
]

INSCRIPTION_PIKE_CHOICES = [
    ('', '—'),
    ('Piquet blanc', 'Piquet blanc'),
    ('Piquet bleu', 'Piquet bleu'),
    ('Piquet rouge', 'Piquet rouge'),
    ('__custom__', 'Autre…'),
]


def _inscription_weapon_group(weapon_choice, bow_type):
    """CL / CO / BB / LD (arc droit / longbow) pour les tableaux distances-blasons."""
    w = _registration_weapon_canonical(weapon_choice)
    if w == '__fiche__':
        bt_norm = (bow_type or '').lower().strip()
        if bt_norm == 'co' or 'compound' in bt_norm or 'poulie' in bt_norm:
            return 'CO'
        if (
            bt_norm in ('ld', 'ad', 'longbow')
            or 'longbow' in bt_norm
            or 'arc droit' in bt_norm
            or bt_norm == 'long bow'
        ):
            return 'LD'
        if bt_norm == 'bb' or 'bare' in bt_norm:
            return 'BB'
        if bt_norm == 'cl':
            return 'CL'
        return 'CL'
    if w in ('Compound', 'CO'):
        return 'CO'
    if w in ('Longbow', 'LD'):
        return 'LD'
    if w == 'BB':
        return 'BB'
    return 'CL'


def _normalize_inscription_category_key(raw):
    """Associe le libellé catégorie (fiche ou saisie) à une clé du tableau U11…U21_SPLUS."""
    if raw is None:
        return None
    s = str(raw).strip().upper().replace('É', 'E').replace('È', 'E')
    if not s:
        return None
    s_nospace = re.sub(r'\s+', '', s)
    if re.search(r'\bU21\b', s) or s_nospace == 'U21':
        return 'U21_SPLUS'
    if re.search(r'SENIOR\s*3|SNR\s*3', s) or s_nospace in ('S3', 'SENIOR3', 'SÉNIOR3'):
        return 'U21_SPLUS'
    if re.search(r'SENIOR\s*2|SNR\s*2', s) or s_nospace in ('S2', 'SENIOR2', 'SÉNIOR2'):
        return 'U21_SPLUS'
    if re.search(r'SENIOR\s*1|SNR\s*1', s) or s_nospace in ('S1', 'SENIOR1', 'SÉNIOR1'):
        return 'U21_SPLUS'
    if 'SENIOR' in s and re.search(r'[123]', s):
        return 'U21_SPLUS'
    if re.search(r'\bU18\b', s) or s_nospace == 'U18':
        return 'U18'
    if re.search(r'\bU15\b', s) or s_nospace == 'U15':
        return 'U15'
    if re.search(r'\bU13\b', s) or s_nospace == 'U13':
        return 'U13'
    if re.search(r'\bU11\b', s) or s_nospace == 'U11':
        return 'U11'
    if re.match(r'^S[123]$', s.strip()):
        return 'U21_SPLUS'
    return None


def _normalize_inscription_category_key_exterieur_di(raw):
    """
    Clés pour tableaux extérieur DI et DN (U21 + S1/S2 ≠ S3 quand le règlement le prévoit).
    """
    if raw is None:
        return None
    s = str(raw).strip().upper().replace('É', 'E').replace('È', 'E')
    if not s:
        return None
    s_nospace = re.sub(r'\s+', '', s)
    if re.search(r'SENIOR\s*3|SNR\s*3', s) or s_nospace in ('S3', 'SENIOR3', 'SÉNIOR3'):
        return 'S3'
    if re.search(r'\bU18\b', s) or s_nospace == 'U18':
        return 'U18'
    if re.search(r'\bU15\b', s) or s_nospace == 'U15':
        return 'U15'
    if re.search(r'\bU13\b', s) or s_nospace == 'U13':
        return 'U13'
    if re.search(r'\bU11\b', s) or s_nospace == 'U11':
        return 'U11'
    if re.search(r'\bU21\b', s) or s_nospace == 'U21':
        return 'U21_S12'
    if re.search(r'SENIOR\s*1|SNR\s*1', s) or s_nospace in ('S1', 'SENIOR1', 'SÉNIOR1'):
        return 'U21_S12'
    if re.search(r'SENIOR\s*2|SNR\s*2', s) or s_nospace in ('S2', 'SENIOR2', 'SÉNIOR2'):
        return 'U21_S12'
    if re.match(r'^S[12]$', s.strip()):
        return 'U21_S12'
    return None


def _inscription_effective_category_label(archer, age_code, age_custom):
    ac = (age_code or '').strip() or '__fiche__'
    if ac == '__fiche__':
        return (archer.categorie or '').strip()
    if ac == '__custom__':
        return (age_custom or '').strip() or (archer.categorie or '').strip()
    return ac.strip()


def _inscription_unpack_distance_blason_tuple(t):
    """Tuple (dist, blason) ou (dist, '__custom__', texte) → champs formulaire."""
    out = {
        'distance': '',
        'distance_custom': '',
        'blason': '',
        'blason_custom': '',
    }
    if not t:
        return out
    dist = t[0]
    preset_dist = {c for c, _ in INSCRIPTION_DISTANCE_CHOICES if c not in ('', '__custom__')}
    if dist in preset_dist:
        out['distance'] = dist
    else:
        out['distance'] = '__custom__'
        out['distance_custom'] = dist or ''
    if len(t) == 2:
        b = t[1]
        bpreset = {c for c, _ in INSCRIPTION_BLASON_CHOICES if c not in ('', '__custom__')}
        if b in bpreset:
            out['blason'] = b
        elif b:
            out['blason'] = '__custom__'
            out['blason_custom'] = b
    elif len(t) >= 3:
        out['blason'] = '__custom__'
        out['blason_custom'] = (t[2] or '').strip()
    return out


def _inscription_targets_table_for_discipline(discipline_code):
    disc = _inscription_discipline_canonical(discipline_code)
    return INSCRIPTION_TARGET_TABLES_BY_DISCIPLINE.get(disc) or INSCRIPTION_CAT_WEAPON_TARGETS_SALLE


def _inscription_category_key_for_table(eff_label, discipline_code):
    disc = _inscription_discipline_canonical(discipline_code)
    if disc in ('exterieur_di', 'exterieur_dn'):
        return _normalize_inscription_category_key_exterieur_di(eff_label)
    if disc == 'beursault':
        k = _normalize_inscription_category_key(eff_label)
        if k in ('U11',):
            return None
        return k
    if disc == 'campagne':
        k = _normalize_inscription_category_key(eff_label)
        if k in ('U11', None):
            return None
        return k
    return _normalize_inscription_category_key(eff_label)


def _inscription_campagne_auto_fields(archer, age_code, age_custom, weapon_choice):
    """Piquet campagne ; distance/blason vidés (discipline pique)."""
    eff = _inscription_effective_category_label(archer, age_code, age_custom)
    cat_key = _inscription_category_key_for_table(eff, 'campagne')
    if not cat_key:
        return {}
    grp = _inscription_weapon_group(weapon_choice, archer.bow_type)
    row = INSCRIPTION_CAMPAGNE_PIQUETS.get(cat_key)
    if not row:
        return {}
    pval = row.get(grp)
    if grp == 'LD' and pval is None:
        pval = row.get('CL')
    base = {
        'distance': '',
        'distance_custom': '',
        'blason': '',
        'blason_custom': '',
        'pike': '',
        'pike_custom': '',
    }
    presets = {c for c, _ in INSCRIPTION_PIKE_CHOICES if c not in ('', '__custom__')}
    if pval is None:
        return base
    if pval in presets:
        base['pike'] = pval
    else:
        base['pike'] = '__custom__'
        base['pike_custom'] = pval
    return base


def _inscription_campagne_targets_for_json():
    out = {}
    for cat, weapons in INSCRIPTION_CAMPAGNE_PIQUETS.items():
        out[cat] = {g: (None if p is None else [p]) for g, p in weapons.items()}
    return out


def _inscription_default_distance_blason_fields(
    archer, age_code, age_custom, weapon_choice, discipline_code=None
):
    """Remplissage auto distance + blason (ou piquet campagne) selon discipline, catégorie et arme."""
    disc = _inscription_discipline_canonical(discipline_code)
    if disc == 'campagne':
        return _inscription_campagne_auto_fields(archer, age_code, age_custom, weapon_choice)
    eff = _inscription_effective_category_label(archer, age_code, age_custom)
    cat_key = _inscription_category_key_for_table(eff, disc)
    if not cat_key:
        return {}
    grp = _inscription_weapon_group(weapon_choice, archer.bow_type)
    table = _inscription_targets_table_for_discipline(disc)
    row = table.get(cat_key)
    if not row:
        return {}
    tup = row.get(grp)
    if tup is None and grp == 'LD':
        tup = row.get('CL')
    if tup is None:
        return {}
    return _inscription_unpack_distance_blason_tuple(tup)


def _inscription_cat_weapon_targets_for_json():
    """Par discipline : clés catégorie → groupe d’arc → liste ou null (CO non régi)."""

    def serialize_table(tbl):
        out = {}
        for cat, weapons in tbl.items():
            out[cat] = {}
            for g, t in weapons.items():
                if t is None:
                    out[cat][g] = None
                elif len(t) == 2:
                    out[cat][g] = [t[0], t[1]]
                else:
                    out[cat][g] = [t[0], '__custom__', t[2]]
        return out

    return {
        'salle': serialize_table(INSCRIPTION_CAT_WEAPON_TARGETS_SALLE),
        'exterieur_di': serialize_table(INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DI),
        'exterieur_dn': serialize_table(INSCRIPTION_CAT_WEAPON_TARGETS_EXTERIEUR_DN),
        'beursault': serialize_table(INSCRIPTION_CAT_WEAPON_TARGETS_BEURSAULT),
    }


def _inscription_discipline_mode(code):
    code = _inscription_discipline_canonical(code)
    for c, _lbl, mode in INSCRIPTION_DISCIPLINES:
        if c == code:
            return mode
    return 'both'


def _inscription_discipline_label(code):
    code = _inscription_discipline_canonical(code)
    for c, lbl, _m in INSCRIPTION_DISCIPLINES:
        if c == code:
            return lbl
    return (code or '').strip() or '—'


def _inscription_select_or_custom(raw, custom_key, aid):
    """raw = valeur du select ; si __custom__, lit request.form[custom_key_aid]."""
    v = (raw or '').strip()
    if v == '__custom__':
        return (request.form.get(f'{custom_key}_{aid}', '') or '').strip()
    return v


def _inscription_age_label(archer, age_code):
    ac = (age_code or '').strip() or '__fiche__'
    if ac == '__fiche__':
        return (archer.categorie or '').strip() or '—'
    if ac == '__custom__':
        return (request.form.get(f'age_custom_{archer.id}', '') or '').strip() or '—'
    return ac


def _inscription_blason_label(aid, blason_sel):
    sel = (blason_sel or '').strip()
    if sel == '__custom__':
        return (request.form.get(f'blason_custom_{aid}', '') or '').strip() or '—'
    return sel or '—'


def _inscription_distance_value(aid):
    d = (request.form.get(f'distance_{aid}', '') or '').strip()
    return _inscription_select_or_custom(d, 'distance_custom', aid)


def _inscription_pike_value(aid):
    p = (request.form.get(f'pike_{aid}', '') or '').strip()
    return _inscription_select_or_custom(p, 'pike_custom', aid)


def _inscription_dist_pike_summary(disc_code, distance_str, pike_str):
    mode = _inscription_discipline_mode(disc_code)
    d = (distance_str or '').strip()
    p = (pike_str or '').strip()
    if mode == 'distance':
        return d or '—'
    if mode == 'pike':
        return p or '—'
    bits = []
    if d:
        bits.append(d)
    if p:
        bits.append(p if p.lower().startswith('pique') else f'Pique {p}')
    return ' — '.join(bits) if bits else '—'


def _inscription_parse_row(archer):
    """Lit le POST pour une ligne archer (tous champs d'inscription)."""
    aid = archer.id
    disc = _inscription_discipline_canonical(request.form.get(f'discipline_{aid}', ''))
    age_code = (request.form.get(f'age_category_{aid}', '') or '').strip() or '__fiche__'
    w = _registration_weapon_canonical(request.form.get(f'weapon_{aid}', '__fiche__'))
    blason_sel = request.form.get(f'blason_{aid}', '')
    dist = _inscription_distance_value(aid)
    pike = _inscription_pike_value(aid)
    weapon_label = _inscription_mail_weapon_abbrev(archer, w)
    _wl = (weapon_label or '').strip()
    if not _wl or _wl in ('—', '-', '\u2014'):
        weapon_label = 'CL'
    age_label = _inscription_age_label(archer, age_code)
    blason_label = _inscription_blason_label(aid, blason_sel)
    dist_pike = _inscription_dist_pike_summary(disc, dist, pike)
    return {
        'discipline_code': disc,
        'discipline_label': _inscription_discipline_label(disc),
        'weapon_choice': w,
        'weapon_label': weapon_label,
        'age_code': age_code,
        'age_label': age_label,
        'blason_label': blason_label,
        'distance_stored': dist,
        'pike_stored': pike,
        'dist_pike_label': dist_pike,
        'depart_index': _inscription_parse_depart_index(aid),
    }


def _inscription_age_for_db(archer, age_code):
    ac = (age_code or '').strip() or '__fiche__'
    if ac == '__fiche__':
        return None
    if ac == '__custom__':
        return (request.form.get(f'age_custom_{archer.id}', '') or '').strip() or None
    return ac


def _inscription_blason_for_db(aid, blason_sel):
    sel = (blason_sel or '').strip()
    if not sel:
        return None
    if sel == '__custom__':
        return (request.form.get(f'blason_custom_{aid}', '') or '').strip() or None
    return sel


def _preset_match(stored, choices):
    stored = (stored or '').strip()
    if not stored:
        return '', ''
    presets = {c for c, _ in choices if c not in ('', '__custom__')}
    if stored in presets:
        return stored, ''
    return '__custom__', stored


def _inscription_row_form_state(archer, reg=None, depart_option_count=1):
    """État formulaire pour un archer (depuis DB ou défauts)."""
    dc = max(1, int(depart_option_count or 1))
    if reg is None:
        st = {
            'discipline': DEFAULT_INSCRIPTION_DISCIPLINE,
            'age_category': '__fiche__',
            'age_custom': '',
            'blason': '',
            'blason_custom': '',
            'distance': '',
            'distance_custom': '',
            'pike': '',
            'pike_custom': '',
            'depart_index': 0,
        }
        auto = _inscription_default_distance_blason_fields(
            archer, '__fiche__', '', '__fiche__', st['discipline']
        )
        st.update(auto)
        return st
    disc = _inscription_discipline_canonical(reg.discipline)
    if reg.age_category is None or (reg.age_category or '').strip() == '':
        age_cat, age_cust = '__fiche__', ''
    else:
        age_cat, age_cust = _preset_match(reg.age_category, INSCRIPTION_AGE_CATEGORY_CHOICES)
    blason, blason_cust = _preset_match(
        _inscription_blason_canonical(reg.blason or ''), INSCRIPTION_BLASON_CHOICES
    )
    dist, dist_cust = _preset_match(reg.distance_label or '', INSCRIPTION_DISTANCE_CHOICES)
    pike, pike_cust = _preset_match(reg.pike_label or '', INSCRIPTION_PIKE_CHOICES)
    di = 0
    if reg.depart_index is not None:
        try:
            di = int(reg.depart_index)
        except (TypeError, ValueError):
            di = 0
    di = _inscription_clamp_depart_index(di, dc)
    return {
        'discipline': disc,
        'age_category': age_cat or '__fiche__',
        'age_custom': age_cust,
        'blason': blason,
        'blason_custom': blason_cust,
        'distance': dist,
        'distance_custom': dist_cust,
        'pike': pike,
        'pike_custom': pike_cust,
        'depart_index': di,
    }


app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'your-secret-key-change-this'  # À changer en production
db.init_app(app)
migrate = Migrate(app, db)

# Initialiser Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vous devez vous connecter pour accéder à cette page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Décorateurs de permission
def require_permission(permission_type):
    """Décorateur pour vérifier les permissions de l'utilisateur"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Vous devez vous connecter.', 'error')
                return redirect(url_for('login'))
            
            # Vérifications spécifiques par type de permission
            if permission_type == 'admin' and not current_user.is_admin():
                flash('Seuls les administrateurs peuvent effectuer cette action.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'delete' and not current_user.can_delete():
                flash('Seuls les administrateurs peuvent supprimer les données.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'edit' and not current_user.can_edit():
                flash('Vous n\'avez pas la permission pour modifier cette donnée.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'manage_courses' and not current_user.can_manage_courses():
                flash('Seuls les responsables et administrateurs peuvent gérer les cours.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'manage_attendance' and not current_user.can_manage_attendance():
                flash('Vous n\'avez pas la permission pour gérer les présences.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'view_equipment' and not current_user.can_view_equipment():
                flash('Vous n\'avez pas la permission pour voir le matériel.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'manage_assignments_for_coach' and not current_user.can_manage_assignments_for_coach():
                flash('Vous n\'avez pas la permission pour gérer les assignations.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'view_courses' and not current_user.can_view_courses():
                flash('Vous n\'avez pas la permission pour voir les cours.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'manage_assignments' and not current_user.can_manage_assignments():
                flash('Vous n\'avez pas la permission pour gérer les assignations.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'view_assignments' and not current_user.can_view_assignments():
                flash('Vous n\'avez pas la permission pour voir les assignations.', 'error')
                return redirect(url_for('index'))
            
            elif permission_type == 'view' and not current_user.can_view():
                flash('Vous n\'avez pas la permission pour voir cette page.', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_client_ip():
    """IP client : premier hop X-Forwarded-For (proxy de confiance), sinon remote_addr."""
    xff = (request.headers.get('X-Forwarded-For') or '').strip()
    if xff:
        part = xff.split(',')[0].strip()
        if part:
            return part[:45]
    addr = request.remote_addr or ''
    return (addr or 'unknown')[:45]


def _record_login_event(*, user_id, attempted_username, success):
    try:
        ua = request.headers.get('User-Agent') or None
        if ua and len(ua) > 4000:
            ua = ua[:4000]
        db.session.add(
            UserLoginEvent(
                user_id=user_id,
                attempted_username=attempted_username,
                success=success,
                ip_address=get_client_ip(),
                user_agent=ua,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Impossible d'enregistrer l'événement de connexion")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        uname_audit = (username[:80] if username else None)

        user = User.query.filter_by(username=username).first() if username else None
        if user and user.check_password(password):
            login_user(user)
            _record_login_event(user_id=user.id, attempted_username=None, success=True)
            return redirect(url_for('index'))
        _record_login_event(
            user_id=(user.id if user else None),
            attempted_username=(None if user else uname_audit),
            success=False,
        )
        return render_template('login.html', error='Nom d\'utilisateur ou mot de passe incorrect')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def _decode_csv_bytes(raw: bytes) -> str:
    """
    Décode un CSV (import archers, etc.).

    Ordre : UTF-16 avec BOM, UTF-8 avec BOM (Excel « CSV UTF-8 »), puis **Windows-1252**
    (cp1252, « Western European (Windows) » — encodage par défaut d’Excel pour un CSV
    classique en France), puis UTF-8 sans BOM et autres pages Latin.
    """
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16-sig')
    # utf-8-sig = UTF-8 avec BOM ; cp1252 = Windows-1252 avant utf-8 nu (exports Excel FR)
    for encoding in (
        'utf-8-sig',
        'cp1252',
        'utf-8',
        'cp1250',
        'iso-8859-15',
        'iso-8859-1',
    ):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _detect_csv_delimiter(content: str) -> str:
    """Point-virgule (Excel FR), virgule ou tabulation selon le fichier."""
    sample = (content[:8192] if content else '').strip()
    if not sample:
        return ';'
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=';,\t|')
        return dialect.delimiter
    except csv.Error:
        pass
    first = content.splitlines()[0] if content.splitlines() else ''
    sc = first.count(';')
    cc = first.count(',')
    if cc > sc:
        return ','
    return ';'


def _make_unique_csv_fieldnames(headers):
    """Évite les clés dupliquées (ex. deux colonnes « Catégorie ») qui écrasent les valeurs dans DictReader."""
    seen = {}
    out = []
    for h in headers:
        key = (h or '').strip()
        n = seen.get(key, 0) + 1
        seen[key] = n
        out.append(key if n == 1 else f'{key}_{n}')
    return out


_IMPORT_LICENSE_RE = re.compile(r'^[0-9]{5,}[A-Za-z0-9-]*$')


def _split_nom_prenom_combined_cell(cell: str):
    """
    Découpe une cellule « nom + prénom » (export FFTA / club).

    - Civilités M / Me / Mme / Mr en tête retirées.
    - Forme « NOM, Prénom » (virgule) : coupure sur la première virgule.
    - 3+ mots séparés par espaces : tout sauf le dernier = nom, dernier = prénom
      (ex. VAN DER BERG Jean).
    - 2 mots : ordre FFTA habituel **NOM puis Prénom** (ex. BENZ LOUIS, ANTOINE THOMAS).
    """
    s = (cell or '').strip()
    if not s:
        return '', ''
    lower = s.lower()
    for prefix in ('mme ', 'mlle ', 'me ', 'mr ', 'm '):
        if lower.startswith(prefix):
            s = s[len(prefix):].strip()
            lower = s.lower()
            break
    if ',' in s:
        left, _, right = s.partition(',')
        left, right = left.strip(), right.strip()
        if left and right:
            return left, right
    parts = s.split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    if len(parts) == 2:
        a, b = parts[0], parts[1]
        return a, b
    return ' '.join(parts[:-1]), parts[-1]


def _header_is_nom_prenom_combine(norm_key: str) -> bool:
    nk = norm_key.replace(',', ' ').replace(';', ' ')
    nk = ' '.join(nk.split())
    parts = nk.split()
    return 'nom' in parts and 'prenom' in parts


def _split_composite_csv_component_cell(cell):
    """
    Découpe une cellule d'export du type « Marque (Catégorie) | Marque2 (Cat2) ».
    Retourne une liste de (marque, nom_catégorie).
    """
    if cell is None or not str(cell).strip():
        return []
    s = str(cell).strip()
    parts = [p.strip() for p in s.split(' | ') if p.strip()]
    out = []
    for p in parts:
        idx = p.rfind(' (')
        if idx < 0:
            continue
        brand = p[:idx].strip()
        rest = p[idx + 2 :].strip()
        if not rest.endswith(')'):
            continue
        cat = rest[:-1].strip()
        if brand and cat:
            out.append((brand, cat))
    return out


def _normalize_composite_type_import(raw):
    s = (raw or '').strip().upper()
    if not s:
        return None
    if s in ('BB', 'BAREBOW', 'BARE BOW'):
        return 'BB'
    if s in ('CL', 'CLASSIQUE'):
        return 'CL'
    return s if len(s) <= 10 else s[:10]


def _normalize_composite_status_import(raw):
    s = (raw or '').strip().lower()
    if s in ('', 'club', 'au club'):
        return 'club'
    if s in ('loan', 'en prêt', 'en pret', 'prêt', 'pret', 'prêté', 'prete'):
        return 'loan'
    return 'club'


def _truncate_db_str(s, max_len):
    t = (s or '').strip()
    if len(t) <= max_len:
        return t, False
    return t[:max_len], True


def _find_or_create_category_for_composite_import(cat_name):
    """
    Catégorie existante (ilike) ou création avec défauts alignés sur add_category.
    Retourne (Category | None, created: bool).
    """
    cn = (cat_name or '').strip()
    if not cn:
        return None, False
    name_db, _trunc = _truncate_db_str(cn, 50)
    existing = Category.query.filter(Category.name.ilike(name_db)).first()
    if existing:
        return existing, False
    max_pos = db.session.query(func.max(Category.position)).scalar() or 0
    cat = Category(
        name=name_db,
        position=max_pos + 1,
        has_size=False,
        has_power=False,
        has_model=True,
        has_brand=True,
        custom_fields='',
        field_units=None,
    )
    db.session.add(cat)
    db.session.flush()
    return cat, True


def _get_or_create_product_for_composite_import(brand, cat_name):
    """
    Produit existant ou création (stock / club). Catégorie créée si besoin.
    Retourne (Product | None, created_product, created_category, ambiguous_multiples).
    """
    brand_db, _btrunc = _truncate_db_str(brand, 50)
    if not brand_db:
        return None, False, False, False
    cat, created_cat = _find_or_create_category_for_composite_import(cat_name)
    if not cat:
        return None, False, False, False
    prods = (
        Product.query.filter(
            Product.category_id == cat.id,
            Product.brand.ilike(brand_db),
        )
        .order_by(Product.id)
        .all()
    )
    if len(prods) > 1:
        return prods[0], False, created_cat, True
    if len(prods) == 1:
        return prods[0], False, created_cat, False
    prod = Product(
        category_id=cat.id,
        brand=brand_db,
        state='stock',
        location='club',
    )
    db.session.add(prod)
    db.session.flush()
    return prod, True, created_cat, False


def _sync_composite_components_from_products(comp, new_products, *, is_new):
    """
    Attache les produits à l'arc en répliquant la logique add_composite / edit_composite
    (retrait sur l'autre arc non prêté, swap de catégorie si édition).
    """
    if is_new:
        for prod in new_products:
            for other in list(prod.composites):
                if other.id != comp.id and other.status != 'loan':
                    old_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                    other.components.remove(prod)
                    new_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                    if old_other != new_other:
                        log_history(
                            event_type='composite_change',
                            entity_type='composite',
                            entity_id=other.id,
                            summary=f"Pièce déplacée vers {comp.name}",
                            details={'before': old_other, 'after': new_other},
                        )
                    break
            comp.components.append(prod)
        return
    old_by_cat = {p.category.id: p for p in comp.components if p.category}
    for newp in new_products:
        for other in list(newp.composites):
            if other.id != comp.id and other.status != 'loan':
                old_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                other.components.remove(newp)
                cat_id = newp.category.id if newp.category else None
                oldp = old_by_cat.get(cat_id)
                if oldp and oldp != newp:
                    other.components.append(oldp)
                new_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                if old_other != new_other:
                    log_history(
                        event_type='composite_change',
                        entity_type='composite',
                        entity_id=other.id,
                        summary=f"Swap de composant via {comp.name}",
                        details={'before': old_other, 'after': new_other},
                    )
                break
    comp.components.clear()
    for prod in new_products:
        comp.components.append(prod)


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

@app.route('/')
@login_required
def index():
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
@login_required
def categories():
    cats = Category.query.order_by(Category.position.asc(), Category.name.asc()).all()
    return render_template('categories.html', categories=cats)

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def add_category():
    if request.method == 'POST':
        name = request.form['name']
        has_size = 'has_size' in request.form
        has_power = 'has_power' in request.form
        has_model = 'has_model' in request.form
        has_brand = 'has_brand' in request.form
        # Convertir les champs personnalisés (un par ligne) en virgules séparées, en préservant la partie après ":"
        custom_fields_raw = request.form.get('custom_fields', '').strip()
        custom_fields_lines = [line.strip() for line in custom_fields_raw.split('\n') if line.strip()]
        custom_fields = ','.join(custom_fields_lines)
        # collect units
        field_units = {}
        unit_brand = request.form.get('unit_brand','').strip()
        unit_model = request.form.get('unit_model','').strip()
        unit_size = request.form.get('unit_size','').strip()
        unit_power = request.form.get('unit_power','').strip()
        if unit_brand: field_units['brand'] = unit_brand
        if unit_model: field_units['model'] = unit_model
        if unit_size: field_units['size'] = unit_size
        if unit_power: field_units['power'] = unit_power
        # custom field units: one per line matching custom_fields_lines
        custom_units_raw = request.form.get('custom_field_units','').strip()
        custom_units_lines = [line.strip() for line in custom_units_raw.split('\n') if line.strip()]
        for i, label in enumerate(custom_fields_lines):
            norm = ' '.join(label.split()).lower()
            if i < len(custom_units_lines) and custom_units_lines[i]:
                field_units[norm] = custom_units_lines[i]

        # assign next position
        max_pos = db.session.query(func.max(Category.position)).scalar() or 0
        cat = Category(name=name, has_size=has_size, has_power=has_power, has_model=has_model, has_brand=has_brand, custom_fields=custom_fields, field_units=field_units if field_units else None, position=max_pos+1)
        db.session.add(cat)
        db.session.commit()
        return redirect(url_for('categories'))
    return render_template('add_category.html')

@app.route('/edit_category/<int:cat_id>', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def edit_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if request.method == 'POST':
        cat.name = request.form['name']
        cat.has_size = 'has_size' in request.form
        cat.has_power = 'has_power' in request.form
        cat.has_model = 'has_model' in request.form
        cat.has_brand = 'has_brand' in request.form
        # Convertir les champs personnalisés (un par ligne) en virgules séparées, en préservant la partie après ":"
        custom_fields_raw = request.form.get('custom_fields', '').strip()
        custom_fields_lines = [line.strip() for line in custom_fields_raw.split('\n') if line.strip()]
        cat.custom_fields = ','.join(custom_fields_lines)
        # update units
        field_units = cat.field_units or {}
        unit_brand = request.form.get('unit_brand','').strip()
        unit_model = request.form.get('unit_model','').strip()
        unit_size = request.form.get('unit_size','').strip()
        unit_power = request.form.get('unit_power','').strip()
        if unit_brand: field_units['brand'] = unit_brand
        else: field_units.pop('brand', None)
        if unit_model: field_units['model'] = unit_model
        else: field_units.pop('model', None)
        if unit_size: field_units['size'] = unit_size
        else: field_units.pop('size', None)
        if unit_power: field_units['power'] = unit_power
        else: field_units.pop('power', None)
        # custom field units lines
        custom_units_raw = request.form.get('custom_field_units','').strip()
        custom_units_lines = [line.strip() for line in custom_units_raw.split('\n') if line.strip()]
        for i, label in enumerate(custom_fields_lines):
            norm = ' '.join(label.split()).lower()
            if i < len(custom_units_lines) and custom_units_lines[i]:
                field_units[norm] = custom_units_lines[i]
            else:
                field_units.pop(norm, None)
        cat.field_units = field_units if field_units else None
        db.session.commit()
        return redirect(url_for('categories'))
    return render_template('edit_category.html', category=cat)

@app.route('/delete_category/<int:cat_id>', methods=['POST'])
@login_required
@require_permission('delete')
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    products = Product.query.filter_by(category_id=cat_id).all()
    for prod in products:
        for comp in prod.composites:
            comp.components.remove(prod)
        db.session.delete(prod)
    db.session.delete(cat)
    db.session.commit()
    # renumber positions to keep them contiguous
    cats = Category.query.order_by(Category.position.asc(), Category.id.asc()).all()
    for i, c in enumerate(cats, start=1):
        c.position = i
    db.session.commit()
    return redirect(url_for('categories'))


@app.route('/move_category/<int:cat_id>/<string:direction>', methods=['POST'])
@login_required
@require_permission('edit')
def move_category(cat_id, direction):
    cat = Category.query.get_or_404(cat_id)
    if direction not in ('up', 'down'):
        return redirect(url_for('categories'))
    if direction == 'up':
        neighbor = Category.query.filter(Category.position < cat.position).order_by(Category.position.desc()).first()
    else:
        neighbor = Category.query.filter(Category.position > cat.position).order_by(Category.position.asc()).first()
    if neighbor:
        cat.position, neighbor.position = neighbor.position, cat.position
        db.session.commit()
    return redirect(url_for('categories'))


@app.route('/reorder_categories', methods=['POST'])
@login_required
@require_permission('edit')
def reorder_categories():
    data = request.get_json(silent=True)
    if not data or 'order' not in data:
        return ('', 400)
    try:
        ids = [int(i) for i in data['order']]
    except Exception:
        return ('', 400)

    # update positions according to the provided order
    cats = Category.query.filter(Category.id.in_(ids)).all()
    cat_map = {c.id: c for c in cats}
    pos = 1
    for cid in ids:
        c = cat_map.get(cid)
        if c:
            c.position = pos
            pos += 1

    # append any categories not included in the list
    remaining = Category.query.filter(~Category.id.in_(ids)).order_by(Category.position.asc(), Category.id.asc()).all()
    for c in remaining:
        c.position = pos
        pos += 1

    db.session.commit()
    return ('', 204)

@app.route('/products')
@login_required
@require_permission('view_equipment')
def products():
    # fetch products sorted according to the category position first, then name/brand
    prods = Product.query.join(Category).order_by(Category.position.asc(), Category.name.asc(), Product.brand.asc()).all()
    
    # Group products by category name in the order they appear in the query above
    from collections import defaultdict
    grouped = defaultdict(list)
    for product in prods:
        # category may be None in edge cases, but position should handle that too
        grouped[product.category.name].append(product)
    
    # also supply ordered list of categories for tabs/panels
    cats = Category.query.order_by(Category.position.asc(), Category.name.asc()).all()
    return render_template('products.html', products=prods, grouped_products=grouped, categories=cats)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
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
@login_required
@require_permission('edit')
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
@login_required
@require_permission('edit')
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

def natural_sort_key(s):
    """Extract numbers from string for natural sorting (Arc_2 before Arc_10)"""
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s or '')]

def _first_int_from_text(val):
    """Premier entier dans une chaîne (ex. taille poignée/branche)."""
    if val is None:
        return None
    m = re.search(r'-?\d+', str(val).strip())
    return int(m.group(0)) if m else None

def _product_size_display(product):
    """Chaîne taille + unité catégorie pour un produit."""
    if not product:
        return None
    raw = product.size
    if not raw and product.custom_values:
        raw = product.custom_values.get('size')
    if not raw:
        return None
    cat = product.category
    u = ''
    if cat and cat.field_units and cat.field_units.get('size'):
        u = ' ' + str(cat.field_units.get('size'))
    return f"{raw}{u}"

def _product_power_display(product):
    if not product:
        return None
    raw = product.power
    if not raw and product.custom_values:
        raw = product.custom_values.get('power')
    if not raw:
        return None
    cat = product.category
    u = ''
    if cat and cat.field_units and cat.field_units.get('power'):
        u = ' ' + str(cat.field_units.get('power'))
    return f"{raw}{u}"

@app.route('/composites')
@login_required
def composites():
    # Get sort parameter from query string
    sort_by = request.args.get('sort', 'name')  # default sort by name
    
    comps = CompositeProduct.query.all()
    
    # Sort the composites
    if sort_by == 'type':
        comps = sorted(comps, key=lambda x: x.type or '')
    elif sort_by == 'status':
        comps = sorted(comps, key=lambda x: x.status or '')
    elif sort_by == 'name':
        comps = sorted(comps, key=lambda x: natural_sort_key(x.name))
    
    # Résumé par arc : poignée, branche, puissance (branche), taille AMO = branche + poignée - 25
    summaries = {}
    for comp in comps:
        handle = None
        branch = None
        handle_prod = None
        branch_prod = None
        for p in comp.components:
            cname = (p.category.name or '').lower()
            if 'poign' in cname or 'handle' in cname:
                if not handle:
                    parts = []
                    if p.size:
                        parts.append(str(p.size))
                    if p.custom_values:
                        for k in ('latéralité', 'lateralite', 'side', 'hand', 'lat'):
                            if k in p.custom_values:
                                parts.append(str(p.custom_values[k]))
                                break
                    handle = ' '.join(parts) if parts else p.brand or ''
                if handle_prod is None:
                    handle_prod = p
            if 'branche' in cname or 'branch' in cname or 'limb' in cname:
                if not branch:
                    parts = []
                    if p.model:
                        parts.append(p.model)
                    if p.size:
                        parts.append(str(p.size))
                    if p.power:
                        parts.append(str(p.power))
                    if p.custom_values and not parts:
                        if 'size' in p.custom_values:
                            parts.append(str(p.custom_values['size']))
                        if 'power' in p.custom_values:
                            parts.append(str(p.custom_values['power']))
                    branch = ' '.join(parts) if parts else p.brand or ''
                if branch_prod is None:
                    branch_prod = p
        handle_num = None
        branch_num = None
        if handle_prod:
            handle_num = _first_int_from_text(handle_prod.size)
            if handle_num is None and handle_prod.custom_values:
                handle_num = _first_int_from_text(handle_prod.custom_values.get('size'))
        if branch_prod:
            branch_num = _first_int_from_text(branch_prod.size)
            if branch_num is None and branch_prod.custom_values:
                branch_num = _first_int_from_text(branch_prod.custom_values.get('size'))
        taille = None
        if handle_num is not None and branch_num is not None:
            taille = branch_num + handle_num - 25
        assigned = None
        for a in comp.assignments:
            if not a.date_returned:
                assigned = a.archer.name if a.archer else 'Assigné'
                break
        summaries[comp.id] = {
            'handle': handle,
            'branch': branch,
            'handle_size_display': _product_size_display(handle_prod),
            'branch_size_display': _product_size_display(branch_prod),
            'power_display': _product_power_display(branch_prod),
            'taille': taille,
            'assigned_to': assigned,
        }
    return render_template('composites.html', composites=comps, composite_summaries=summaries, current_sort=sort_by)

@app.route('/add_composite', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def add_composite():
    if request.method == 'POST':
        name = request.form['name']
        type = request.form['type']
        status = request.form['status']
        comp = CompositeProduct(name=name, type=type, status=status)
        db.session.add(comp)
        db.session.commit()  # need comp.id to exist for relationship handling

        # gather components selected by user
        comp_ids = request.form.getlist('components')
        for cid in comp_ids:
            prod = Product.query.get(int(cid))
            if not prod:
                continue

            # if the product belongs to another composite that is not on loan,
            # remove it and log that swap so the other bow loses this piece.
            for other in list(prod.composites):
                if other.id != comp.id and other.status != 'loan':
                    old_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                    other.components.remove(prod)
                    new_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                    if old_other != new_other:
                        log_history(
                            event_type='composite_change',
                            entity_type='composite',
                            entity_id=other.id,
                            summary=f"Pièce déplacée vers {comp.name}",
                            details={'before': old_other, 'after': new_other}
                        )
                    break

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
    # pass categories (ordered by user-defined position) so template can group products by category
    # Show products that are free or mounted on another bow that is not on loan.
    cats = Category.query.order_by(Category.position.asc(), Category.name.asc()).all()
    cats_with_available = []
    for c in cats:
        available = []
        for p in c.products:
            if not p.composites:
                available.append(p)
            else:
                # include if at least one composite containing this product is
                # not the one we're about to create (obviously) and not on loan
                if any(other.status != 'loan' for other in p.composites):
                    available.append(p)
        cats_with_available.append({'id': c.id, 'name': c.name, 'products': available})
    return render_template('add_composite.html', categories=cats_with_available)

@app.route('/edit_composite/<int:comp_id>', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def edit_composite(comp_id):
    comp = CompositeProduct.query.get_or_404(comp_id)
    if request.method == 'POST':
        # snapshot the old components with category information so we can
        # log and possibly swap them back into another bow later.
        old_components = [f"{p.brand} ({p.category.name})" for p in comp.components]
        old_by_cat = {p.category.id: p for p in comp.components if p.category}

        comp.name = request.form['name']
        comp.type = request.form['type']
        comp.status = request.form['status']

        # collect selection but do not immediately clear the relationship, we
        # need to know which new products belonged to other composites so we
        # can perform a swap.
        comp_ids = request.form.getlist('components')

        # prepare a list of product objects from the submitted ids
        new_products = []
        for cid in comp_ids:
            prod = Product.query.get(int(cid))
            if prod:
                new_products.append(prod)

        # handle swapping: for each new product that is currently part of an
        # other composite which is not on loan, remove it from the other and
        # put the old item (if any) back on that composite in the same
        # category.
        for newp in new_products:
            for other in list(newp.composites):
                if other.id != comp.id and other.status != 'loan':
                    # record before/after for logging
                    old_other = [f"{p.brand} ({p.category.name})" for p in other.components]

                    # remove the piece from the other bow
                    other.components.remove(newp)
                    # if we had something in the same category previously,
                    # give it back to the other bow
                    cat_id = newp.category.id if newp.category else None
                    oldp = old_by_cat.get(cat_id)
                    if oldp and oldp != newp:
                        other.components.append(oldp)

                    new_other = [f"{p.brand} ({p.category.name})" for p in other.components]
                    if old_other != new_other:
                        log_history(
                            event_type='composite_change',
                            entity_type='composite',
                            entity_id=other.id,
                            summary=f"Swap de composant via {comp.name}",
                            details={'before': old_other, 'after': new_other}
                        )
                    break

        # now we can safely clear and re-add
        comp.components.clear()
        for prod in new_products:
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
    # When editing a composite we want to offer the user components that are:
    #  1. not part of any composite (completely free),
    #  2. already part of *this* composite (so they can be kept or removed), or
    #  3. part of another composite **that is not currently loaned out**.
    #
    # The third case lets the user take a piece off of a built bow that isn't
    # assigned to an archer yet.  When such an item is selected we will also
    # swap the old component back onto the other bow on save (see POST logic
    # below).
    prods = Product.query.all()
    prods_filtered = []
    for p in prods:
        if (not p.composites) or (p in comp.components):
            prods_filtered.append(p)
        else:
            # look for a composite containing this product that is not the one
            # we're editing and not currently on loan; show it so the user can
            # swap parts between bows
            for other in p.composites:
                if other.id != comp.id and other.status != 'loan':
                    prods_filtered.append(p)
                    break
    # pass categories so template can group products by category (only include filtered products)
    cats = Category.query.order_by(Category.position.asc(), Category.name.asc()).all()
    cats_with_available = []
    for c in cats:
        available = [p for p in prods_filtered if p.category and p.category.id == c.id]
        cats_with_available.append({'id': c.id, 'name': c.name, 'products': available})
    return render_template('edit_composite.html', composite=comp, categories=cats_with_available)

@app.route('/archers')
@login_required
def archers():
    sort_by = request.args.get('sort_by', 'nom')
    sort_order = request.args.get('sort_order', 'asc')
    # filters
    filter_q = request.args.get('q', '').strip()
    filter_course = request.args.get('course_id')
    filter_has_arc = request.args.get('has_arc')  # 'yes'|'no'|None
    filter_category = request.args.get('category')
    filter_min_age = request.args.get('min_age')
    filter_max_age = request.args.get('max_age')
    
    query = Archer.query

    # apply filters
    if filter_q:
        q = f"%{filter_q}%"
        query = query.filter(db.or_(Archer.first_name.ilike(q), Archer.last_name.ilike(q)))

    if filter_category:
        query = query.filter(Archer.categorie == filter_category)

    if filter_min_age:
        try:
            query = query.filter(Archer.age >= int(filter_min_age))
        except ValueError:
            pass
    if filter_max_age:
        try:
            query = query.filter(Archer.age <= int(filter_max_age))
        except ValueError:
            pass

    # filter by course
    if filter_course:
        try:
            cid = int(filter_course)
            query = query.join(Archer.courses).filter(Course.id == cid)
        except Exception:
            pass

    # filter by has arc (active assignment)
    if filter_has_arc in ('yes','no'):
        from sqlalchemy.orm import aliased
        AssignmentAlias = aliased(Assignment)
        if filter_has_arc == 'yes':
            query = query.join(AssignmentAlias, (AssignmentAlias.archer_id == Archer.id) & (AssignmentAlias.date_returned == None))
        else:
            # archers without active assignment
            query = query.outerjoin(AssignmentAlias, (AssignmentAlias.archer_id == Archer.id) & (AssignmentAlias.date_returned == None)).filter(AssignmentAlias.id == None)
    
    # Apply sorting
    if sort_by == 'nom':
        query = query.order_by(Archer.last_name if sort_order == 'asc' else Archer.last_name.desc())
    elif sort_by == 'prenom':
        query = query.order_by(Archer.first_name if sort_order == 'asc' else Archer.first_name.desc())
    elif sort_by == 'age':
        query = query.order_by(Archer.age if sort_order == 'asc' else Archer.age.desc())
    elif sort_by == 'licence':
        query = query.order_by(Archer.license_number if sort_order == 'asc' else Archer.license_number.desc())
    elif sort_by == 'categorie':
        query = query.order_by(Archer.categorie if sort_order == 'asc' else Archer.categorie.desc())
    elif sort_by == 'arc':
        # sort by currently assigned composite name (if any)
        from sqlalchemy.orm import aliased
        AssignmentAlias = aliased(Assignment)
        CompositeAlias = aliased(CompositeProduct)
        # left outer join to include archers without assignment
        query = query.outerjoin(AssignmentAlias, (AssignmentAlias.archer_id == Archer.id) & (AssignmentAlias.date_returned == None)).outerjoin(CompositeAlias, CompositeAlias.id == AssignmentAlias.composite_id)
        if sort_order == 'asc':
            query = query.order_by(CompositeAlias.name.asc().nullsfirst(), Archer.last_name.asc())
        else:
            query = query.order_by(CompositeAlias.name.desc().nullslast(), Archer.last_name.desc())
    elif sort_by == 'course':
        # sort by a course name the archer is enrolled in (left join)
        from sqlalchemy.orm import aliased
        CourseAlias = aliased(Course)
        query = query.outerjoin(CourseAlias, Archer.courses)
        if sort_order == 'asc':
            query = query.order_by(CourseAlias.name.asc().nullsfirst(), Archer.last_name.asc())
        else:
            query = query.order_by(CourseAlias.name.desc().nullslast(), Archer.last_name.desc())
    else:
        query = query.order_by(Archer.last_name.asc())
    
    archs = query.all()
    current_sort = {'by': sort_by, 'order': sort_order}
    # pass filter options
    courses = Course.query.order_by(Course.name).all()
    # distinct categories from archers
    cats = [c[0] for c in db.session.query(Archer.categorie).distinct().order_by(Archer.categorie).all() if c[0]]
    current_filters = {'q': filter_q, 'course_id': filter_course, 'has_arc': filter_has_arc, 'category': filter_category, 'min_age': filter_min_age, 'max_age': filter_max_age}
    return render_template('archers.html', archers=archs, current_sort=current_sort, courses=courses, categories=cats, current_filters=current_filters)

@app.route('/add_archer', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def add_archer():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        license = request.form.get('license')
        age = request.form.get('age') or None
        bow_length = request.form.get('bow_length')
        draw_length = request.form.get('draw_length')
        bow_type = _normalize_archer_bow_type_from_form(request.form.get('bow_type'))
        notes = request.form.get('notes')
        email = _normalize_archer_email(request.form.get('email'))
        arch = Archer(
            first_name=first_name,
            last_name=last_name,
            age=int(age) if age else None,
            license_number=license,
            email=email,
            bow_length=bow_length,
            draw_length=draw_length,
            bow_type=bow_type,
            notes=notes,
        )
        db.session.add(arch)
        db.session.commit()
        return redirect(url_for('archers'))
    return render_template(
        'add_archer.html',
        bow_type_choices=ARCHER_BOW_TYPE_CHOICES,
        bow_type_valid_codes=ARCHER_BOW_TYPE_VALID_CODES,
        bow_type_value='',
    )


@app.route('/edit_archer/<int:archer_id>', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
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
        arch.bow_type = _normalize_archer_bow_type_from_form(request.form.get('bow_type'))
        arch.notes = request.form.get('notes')
        arch.email = _normalize_archer_email(request.form.get('email'))
        db.session.commit()
        return redirect(url_for('archers'))
    return render_template(
        'edit_archer.html',
        archer=arch,
        bow_type_choices=ARCHER_BOW_TYPE_CHOICES,
        bow_type_valid_codes=ARCHER_BOW_TYPE_VALID_CODES,
        bow_type_value=_archer_bow_type_form_value(arch.bow_type),
    )


def _registration_weapon_label(archer, weapon_choice):
    """Libellé arme pour l'inscription : choix explicite ou type d'arc en base."""
    choice = _registration_weapon_canonical(weapon_choice)
    if choice == '__fiche__':
        return (archer.bow_type or '').strip() or '—'
    return REGISTRATION_WEAPON_LABELS.get(choice, choice)


def _inscription_mail_weapon_abbrev(archer, weapon_choice):
    """
    Abréviation arme pour le texte généré (mail / PDF) :
    CL classique, CO poulies, BB barebow, AD arc droit (longbow).
    « Comme sur la fiche » sans type d'arc en base : CL.
    « Comme sur la fiche » avec arc renseigné : même logique que les tableaux (CO/BB/AD/CL).
    """
    w = _registration_weapon_canonical(weapon_choice)
    if w == '__fiche__':
        if not (archer.bow_type or '').strip():
            return 'CL'
        grp = _inscription_weapon_group('__fiche__', archer.bow_type)
        return {'CO': 'CO', 'BB': 'BB', 'LD': 'AD', 'CL': 'CL'}.get(grp, 'CL')
    if w in ('CL', 'Classique'):
        return 'CL'
    if w in ('BB', 'Barebow'):
        return 'BB'
    if w in ('Compound', 'CO'):
        return 'CO'
    if w in ('Longbow', 'LD'):
        return 'AD'
    if w == 'Autre':
        return 'Autre'
    return 'CL'


def _inscription_depart_phrases_from_event(ev):
    """Liste des phrases « départ » (JSON en base ou ancien champ unique)."""
    if not ev:
        return []
    raw = getattr(ev, 'depart_phrases_json', None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    p = (getattr(ev, 'depart_phrase', None) or '').strip()
    return [p] if p else []


def _inscription_depart_phrases_from_form():
    return [p.strip() for p in request.form.getlist('depart_phrases') if p and str(p).strip()]


def _inscription_depart_select_options(deps):
    """(index, libellé court) pour chaque départ non vide ; au moins une entrée."""
    out = []
    for p in deps or []:
        s = (p or '').strip()
        if s:
            out.append((len(out), s[:200]))
    if not out:
        out = [(0, '—')]
    return out


def _inscription_clamp_depart_index(idx, num_departs):
    try:
        i = int(idx)
    except (TypeError, ValueError):
        i = 0
    n = max(1, int(num_departs or 1))
    return max(0, min(i, n - 1))


def _inscription_parse_depart_index(aid):
    opts = _inscription_depart_select_options(_inscription_depart_phrases_from_form())
    return _inscription_clamp_depart_index(request.form.get(f'depart_index_{aid}', '0'), len(opts))


def _inscription_store_depart_phrases_on_event(ev, phrases):
    clean = [p.strip() for p in (phrases or []) if p and str(p).strip()]
    if clean:
        ev.depart_phrases_json = json.dumps(clean, ensure_ascii=False)
        ev.depart_phrase = clean[0][:500]
    else:
        ev.depart_phrases_json = None
        ev.depart_phrase = None


def _inscription_format_mail_depart_intro(depart_phrases):
    parts = [p.strip() for p in (depart_phrases or []) if p and str(p).strip()]
    if not parts:
        return 'Voici les archers que je souhaite inscrire.'
    if len(parts) == 1:
        return f'Voici les archers que je souhaite inscrire pour le départ de {parts[0]}.'
    return 'Voici les archers que je souhaite inscrire, répartis par départ :'


def _parse_inscription_evenement_form():
    """
    Retourne ((recipient, depart_phrases, lieu, blasons_line, rows), None) ou (None, erreur).
    depart_phrases : liste de chaînes.
    rows : liste de tuples (Archer, meta dict pour _format_inscription_archer_line).
    """
    recipient = request.form.get('recipient_name', '').strip()
    depart_phrases = _inscription_depart_phrases_from_form()
    lieu = request.form.get('lieu', '').strip()
    blasons_line = request.form.get('blasons_line', '').strip()
    ids = request.form.getlist('archer_id')
    if not ids:
        return None, 'Sélectionnez au moins un archer.'
    rows = []
    seen = set()
    for sid in ids:
        try:
            aid = int(sid)
        except (TypeError, ValueError):
            continue
        if aid in seen:
            continue
        seen.add(aid)
        arch = Archer.query.get(aid)
        if not arch:
            continue
        rows.append((arch, _inscription_parse_row(arch)))
    if not rows:
        return None, 'Aucun archer valide sélectionné.'
    return (recipient, depart_phrases, lieu, blasons_line, rows), None


def _format_inscription_archer_line(archer, meta):
    lic = (archer.license_number or '').strip() or '—'
    bits = [
        f'- {archer.name}',
        f'Licence : {lic}',
        meta['discipline_label'],
        f"Cat. : {meta['age_label']}",
        f"Arme : {meta['weapon_label']}",
    ]
    b = (meta.get('blason_label') or '').strip()
    if b and b != '—':
        bits.append(f'Blason : {b}')
    dp = (meta.get('dist_pike_label') or '').strip()
    if dp and dp != '—':
        bits.append(dp)
    return ' — '.join(bits)


def _build_inscription_evenement_body(recipient, depart_phrases, lieu, blasons_line, rows):
    """Texte type courrier / mail pour l’organisateur."""
    from collections import defaultdict

    parts = [p.strip() for p in (depart_phrases or []) if p and str(p).strip()]
    r = (recipient or '').strip()
    salut = f'Bonjour {r},' if r else 'Bonjour,'
    lines = [
        salut,
        '',
        _inscription_format_mail_depart_intro(depart_phrases),
    ]
    if (lieu or '').strip():
        lines.append(f'Lieu : {lieu.strip()}.')
    lines.append('')

    if len(parts) <= 1:
        for arch, meta in rows:
            lines.append(_format_inscription_archer_line(arch, meta))
    else:
        n = len(parts)
        by_dep = defaultdict(list)
        for arch, meta in rows:
            idx = _inscription_clamp_depart_index(meta.get('depart_index', 0), n)
            by_dep[idx].append((arch, meta))
        for i, phrase in enumerate(parts):
            archs = by_dep.get(i, [])
            if not archs:
                continue
            lines.append(f'Pour le départ de {phrase} :')
            for arch, meta in archs:
                lines.append(_format_inscription_archer_line(arch, meta))
            lines.append('')
        while lines and lines[-1] == '':
            lines.pop()

    lines.append('')
    bl = (blasons_line or '').strip()
    if bl:
        lines.append(f'Blasons et distances: {bl}')
    return '\n'.join(lines)


def _inscription_form_snapshot(archers_list):
    """Reconstitue l’état formulaire après un POST (texte / PDF)."""
    deps = _inscription_depart_phrases_from_form()
    if not deps:
        deps = ['']
    dep_opts = _inscription_depart_select_options(deps)
    dep_n = len(dep_opts)
    form_values = {
        'title': request.form.get('title', ''),
        'recipient_name': request.form.get('recipient_name', ''),
        'depart_phrases': deps,
        'lieu': request.form.get('lieu', ''),
        'blasons_line': request.form.get('blasons_line', ''),
    }
    selected_ids = set()
    for sid in request.form.getlist('archer_id'):
        try:
            selected_ids.add(int(sid))
        except (TypeError, ValueError):
            pass
    weapon_saved = {}
    registration_extras = {}
    for a in archers_list:
        aid = a.id
        if aid not in selected_ids:
            continue
        weapon_saved[a.id] = _registration_weapon_canonical(
            request.form.get(f'weapon_{aid}', '__fiche__')
        )
        registration_extras[a.id] = {
            'discipline': _inscription_discipline_canonical(
                request.form.get(f'discipline_{aid}', '')
            ),
            'age_category': (request.form.get(f'age_category_{aid}', '') or '').strip() or '__fiche__',
            'age_custom': request.form.get(f'age_custom_{aid}', '') or '',
            'blason': request.form.get(f'blason_{aid}', '') or '',
            'blason_custom': request.form.get(f'blason_custom_{aid}', '') or '',
            'distance': request.form.get(f'distance_{aid}', '') or '',
            'distance_custom': request.form.get(f'distance_custom_{aid}', '') or '',
            'pike': request.form.get(f'pike_{aid}', '') or '',
            'pike_custom': request.form.get(f'pike_custom_{aid}', '') or '',
            'depart_index': _inscription_clamp_depart_index(
                request.form.get(f'depart_index_{aid}', '0'), dep_n
            ),
        }
    return form_values, selected_ids, weapon_saved, registration_extras


def _inscription_archers_by_depart(selected_ids, registration_extras, archers_by_id, dep_n):
    """Liste de listes d'archers : une sous-liste par index de départ (0 .. dep_n-1)."""
    buckets = [[] for _ in range(max(1, int(dep_n or 1)))]
    n = len(buckets)
    for aid in selected_ids:
        arch = archers_by_id.get(aid)
        if not arch:
            continue
        ex = registration_extras.get(aid, {})
        di = _inscription_clamp_depart_index(ex.get('depart_index', 0), n)
        buckets[di].append(arch)
    for lst in buckets:
        lst.sort(key=lambda a: ((a.last_name or '').lower(), (a.first_name or '').lower()))
    return buckets


def _inscription_archers_picker_payload(archers_list, inscription_archer_cat_keys, inscription_archer_cat_keys_di):
    """Données JSON pour ajout d'archers côté client (un archer ne peut être qu'une fois par événement)."""
    out = []
    for a in archers_list:
        out.append(
            {
                'id': a.id,
                'name': a.name,
                'license_number': (a.license_number or '').strip(),
                'categorie': (a.categorie or '').strip(),
                'bow_type': (a.bow_type or '').strip(),
                'fiche_cat_key': inscription_archer_cat_keys.get(a.id, '') or '',
                'fiche_cat_key_di': inscription_archer_cat_keys_di.get(a.id, '') or '',
            }
        )
    return out


@app.route('/inscription_evenement', methods=['GET', 'POST'])
@login_required
def inscription_evenement():
    archers_list = Archer.query.order_by(Archer.last_name.asc(), Archer.first_name.asc()).all()
    events = (
        InscriptionEvent.query.options(selectinload(InscriptionEvent.registrations))
        .order_by(InscriptionEvent.created_at.desc())
        .all()
    )
    generated_text = None
    current_event = None
    form_values = {
        'title': '',
        'recipient_name': '',
        'depart_phrases': [''],
        'lieu': '',
    }
    selected_ids = set()
    weapon_saved = {}
    registration_extras = {}

    if request.method == 'POST':
        action = request.form.get('action') or ''

        if action == 'create_event':
            title = (request.form.get('new_event_title') or '').strip() or 'Événement'
            ev = InscriptionEvent(
                title=title,
            )
            db.session.add(ev)
            db.session.commit()
            flash('Événement créé. Ajoutez des archers par départ puis enregistrez.', 'success')
            return redirect(url_for('inscription_evenement', event_id=ev.id))

        if action == 'save_event':
            eid = request.form.get('event_id', type=int)
            ev = InscriptionEvent.query.get(eid) if eid else None
            if not ev:
                flash('Événement introuvable.', 'error')
                return redirect(url_for('inscription_evenement'))
            ev.title = (request.form.get('title') or '').strip() or ev.title
            ev.recipient_name = (request.form.get('recipient_name') or '').strip() or None
            _inscription_store_depart_phrases_on_event(
                ev, request.form.getlist('depart_phrases')
            )
            ev.lieu = (request.form.get('lieu') or '').strip() or None
            ev.blasons_line = (request.form.get('blasons_line') or '').strip() or None
            InscriptionEventRegistration.query.filter_by(event_id=ev.id).delete()
            seen = set()
            for sid in request.form.getlist('archer_id'):
                try:
                    aid = int(sid)
                except (TypeError, ValueError):
                    continue
                if aid in seen:
                    continue
                seen.add(aid)
                arch = Archer.query.get(aid)
                if not arch:
                    continue
                w = _registration_weapon_canonical(request.form.get(f'weapon_{aid}', '__fiche__'))
                disc = _inscription_discipline_canonical(request.form.get(f'discipline_{aid}', ''))
                age_db = _inscription_age_for_db(arch, request.form.get(f'age_category_{aid}', '__fiche__'))
                blason_db = _inscription_blason_for_db(aid, request.form.get(f'blason_{aid}', ''))
                dist = _inscription_distance_value(aid) or None
                pike = _inscription_pike_value(aid) or None
                db.session.add(
                    InscriptionEventRegistration(
                        event_id=ev.id,
                        archer_id=aid,
                        weapon_choice=w,
                        discipline=disc,
                        age_category=age_db,
                        blason=blason_db,
                        distance_label=dist,
                        pike_label=pike,
                        depart_index=_inscription_parse_depart_index(aid),
                    )
                )
            db.session.commit()
            flash('Événement et inscriptions enregistrés.', 'success')
            return redirect(url_for('inscription_evenement', event_id=ev.id))

        if action == 'delete_event':
            eid = request.form.get('event_id', type=int)
            ev = InscriptionEvent.query.get(eid) if eid else None
            if ev:
                db.session.delete(ev)
                db.session.commit()
                flash('Événement supprimé.', 'success')
            nxt = InscriptionEvent.query.order_by(InscriptionEvent.created_at.desc()).first()
            if nxt:
                return redirect(url_for('inscription_evenement', event_id=nxt.id))
            return redirect(url_for('inscription_evenement'))

        if action == 'texte':
            form_values, selected_ids, weapon_saved, registration_extras = _inscription_form_snapshot(
                archers_list
            )
            parsed, err = _parse_inscription_evenement_form()
            if err:
                flash(err, 'error')
            else:
                recipient, depart_phrases, lieu, blasons_line, rows = parsed
                generated_text = _build_inscription_evenement_body(
                    recipient, depart_phrases, lieu, blasons_line, rows
                )
            peid = request.form.get('event_id', type=int)
            if peid:
                current_event = InscriptionEvent.query.get(peid)

    if request.method == 'GET':
        eid = request.args.get('event_id', type=int)
        if eid:
            current_event = InscriptionEvent.query.get(eid)
            if not current_event:
                flash('Événement inconnu.', 'error')
        # Sans ?event_id= : afficher la liste des événements (pas de sélection auto)
        if current_event:
            deps = _inscription_depart_phrases_from_event(current_event)
            form_values = {
                'title': current_event.title or '',
                'recipient_name': current_event.recipient_name or '',
                'depart_phrases': deps if deps else [''],
                'lieu': current_event.lieu or '',
                'blasons_line': (current_event.blasons_line or '').strip()
            }
            selected_ids = {r.archer_id for r in current_event.registrations}
            weapon_saved = {
                r.archer_id: _registration_weapon_canonical(r.weapon_choice or '__fiche__')
                for r in current_event.registrations
            }
            reg_by_archer = {r.archer_id: r for r in current_event.registrations}
            dep_opts = _inscription_depart_select_options(deps if deps else [''])
            dep_n = len(dep_opts)
            registration_extras = {
                a.id: _inscription_row_form_state(a, reg_by_archer.get(a.id), dep_n)
                for a in archers_list
                if a.id in selected_ids
            }

    inscription_discipline_modes = {c: m for c, _lbl, m in INSCRIPTION_DISCIPLINES}
    inscription_archer_cat_keys = {
        a.id: (_normalize_inscription_category_key((a.categorie or '').strip()) or '')
        for a in archers_list
    }
    inscription_archer_cat_keys_di = {
        a.id: (
            _normalize_inscription_category_key_exterieur_di((a.categorie or '').strip()) or ''
        )
        for a in archers_list
    }
    inscription_cat_weapon_targets = _inscription_cat_weapon_targets_for_json()
    inscription_campagne_piquets = _inscription_campagne_targets_for_json()
    inscription_depart_options = _inscription_depart_select_options(
        form_values.get('depart_phrases') or ['']
    )
    archers_by_id = {a.id: a for a in archers_list}
    dep_n = len(inscription_depart_options)
    archers_by_depart = _inscription_archers_by_depart(
        selected_ids, registration_extras, archers_by_id, dep_n
    )
    inscription_archers_picker = _inscription_archers_picker_payload(
        archers_list, inscription_archer_cat_keys, inscription_archer_cat_keys_di
    )
    inscription_new_row_extras = (
        _inscription_row_form_state(archers_list[0], None, dep_n) if archers_list else {}
    )

    return render_template(
        'inscription_evenement.html',
        weapon_choices=REGISTRATION_WEAPON_CHOICES,
        generated_text=generated_text,
        form_values=form_values,
        selected_ids=selected_ids,
        weapon_saved=weapon_saved,
        registration_extras=registration_extras,
        events=events,
        current_event=current_event,
        inscription_disciplines=INSCRIPTION_DISCIPLINES,
        inscription_discipline_modes=inscription_discipline_modes,
        inscription_age_choices=INSCRIPTION_AGE_CATEGORY_CHOICES,
        inscription_blason_choices=INSCRIPTION_BLASON_CHOICES,
        inscription_distance_choices=INSCRIPTION_DISTANCE_CHOICES,
        inscription_pike_choices=INSCRIPTION_PIKE_CHOICES,
        inscription_archer_cat_keys=inscription_archer_cat_keys,
        inscription_archer_cat_keys_di=inscription_archer_cat_keys_di,
        inscription_cat_weapon_targets=inscription_cat_weapon_targets,
        inscription_campagne_piquets=inscription_campagne_piquets,
        inscription_depart_options=inscription_depart_options,
        archers_by_depart=archers_by_depart,
        inscription_archers_picker=inscription_archers_picker,
        has_archers=bool(archers_list),
        inscription_new_row_extras=inscription_new_row_extras,
    )


@app.route('/inscription_evenement/pdf', methods=['POST'])
@login_required
def inscription_evenement_pdf():
    parsed, err = _parse_inscription_evenement_form()
    if err:
        flash(err, 'error')
        eid = request.form.get('event_id', type=int)
        return redirect(
            url_for('inscription_evenement', event_id=eid) if eid else url_for('inscription_evenement')
        )
    recipient, depart_phrases, lieu, blasons_line, rows = parsed
    body = _build_inscription_evenement_body(
        recipient, depart_phrases, lieu, blasons_line, rows
    )
    try:
        from io import BytesIO
        from weasyprint import HTML, CSS

        html = render_template('inscription_evenement_pdf.html', body_text=body)
        css = CSS(
            string='''
            @page { margin: 2cm; size: A4; }
            body {
              font-family: "DejaVu Serif", "Liberation Serif", Georgia, serif;
              font-size: 11pt;
              line-height: 1.45;
              color: #1a1a1a;
            }
            .letter {
              white-space: pre-wrap;
              word-wrap: break-word;
            }
            '''
        )
        buffer = BytesIO()
        HTML(string=html).write_pdf(target=buffer, stylesheets=[css])
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='inscription.pdf', mimetype='application/pdf')
    except Exception:
        import textwrap
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=(595, 842))
        y = 800
        x = 72
        for para in body.split('\n'):
            if not para.strip():
                y -= 10
                continue
            for chunk in textwrap.wrap(para, width=88):
                if y < 72:
                    p.showPage()
                    y = 800
                p.drawString(x, y, chunk[:200])
                y -= 14
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='inscription.pdf', mimetype='application/pdf')


@app.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q:
        flash('Veuillez saisir un terme de recherche.', 'info')
        return redirect(url_for('index'))

    term = f"%{q}%"

    products = Product.query.filter(
        db.or_(Product.brand.ilike(term), Product.model.ilike(term), Product.comments.ilike(term))
    ).order_by(Product.brand).limit(200).all()

    archers = Archer.query.filter(
        db.or_(
            Archer.first_name.ilike(term),
            Archer.last_name.ilike(term),
            Archer.license_number.ilike(term),
            Archer.email.ilike(term),
            Archer.notes.ilike(term),
        )
    ).order_by(Archer.last_name).limit(200).all()

    categories = Category.query.filter(Category.name.ilike(term)).all()

    composites = CompositeProduct.query.filter(CompositeProduct.name.ilike(term)).all()

    users = User.query.filter(User.username.ilike(term)).all()

    return render_template('search_results.html', q=q, products=products, archers=archers, categories=categories, composites=composites, users=users)

@app.route('/assignments')
@login_required
@require_permission('view_assignments')
def assignments():
    assigns = Assignment.query.filter_by(date_returned=None).all()
    return render_template('assignments.html', assignments=assigns)

@app.route('/return/<int:assign_id>', methods=['POST'])
@login_required
@require_permission('manage_assignments_for_coach')
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
@login_required
@require_permission('delete')
def delete_archer(archer_id):
    arch = Archer.query.get_or_404(archer_id)
    # Delete associated attendance records
    Attendance.query.filter_by(archer_id=archer_id).delete()
    # Delete associated assignments (cascade will also handle this now)
    Assignment.query.filter_by(archer_id=archer_id).delete()
    db.session.delete(arch)
    db.session.commit()
    return redirect(url_for('archers'))

@app.route('/delete_product/<int:prod_id>', methods=['POST'])
@login_required
@require_permission('delete')
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
@login_required
@require_permission('delete')
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
@login_required
@require_permission('manage_assignments_for_coach')
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
@login_required
@require_permission('manage_assignments_for_coach')
def reset_composite_status(comp_id):
    comp = CompositeProduct.query.get_or_404(comp_id)
    comp.status = 'club'
    db.session.commit()
    return redirect(url_for('assign'))

@app.route('/history')
@login_required
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
@login_required
@require_permission('view_courses')
def courses():
    days_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    courses_list = Course.query.filter_by(active=True).order_by(Course.day_of_week, Course.start_time).all()
    return render_template('courses.html', courses=courses_list, days_names=days_names)

@app.route('/add_course', methods=['GET', 'POST'])
@login_required
@require_permission('manage_courses')
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
@login_required
@require_permission('manage_courses')
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
@login_required
@require_permission('manage_courses')
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    # Soft delete by marking as inactive
    course.active = False
    Attendance.query.filter_by(course_id=course_id).delete()
    db.session.commit()
    return redirect(url_for('courses'))

@app.route('/course/<int:course_id>/archers')
@login_required
@require_permission('manage_courses')
def course_archers(course_id):
    course = Course.query.get_or_404(course_id)
    all_archers = Archer.query.all()
    return render_template('course_archers.html', course=course, all_archers=all_archers)

@app.route('/course/<int:course_id>/add_archer/<int:archer_id>', methods=['POST'])
@login_required
@require_permission('manage_courses')
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
@login_required
@require_permission('manage_courses')
def remove_archer_from_course(course_id, archer_id):
    course = Course.query.get_or_404(course_id)
    archer = Archer.query.get_or_404(archer_id)
    if archer in course.archers:
        course.archers.remove(archer)
        db.session.commit()
    return redirect(url_for('course_archers', course_id=course_id))

@app.route('/course/<int:course_id>/attendance')
@login_required
@require_permission('manage_attendance')
def course_attendance(course_id):
    course = Course.query.get_or_404(course_id)
    today = date.today()
    # Get all attendance records for this course (historical + future)
    attendance_records = Attendance.query.filter(
        Attendance.course_id == course_id
    ).order_by(Attendance.date.desc()).all()
    return render_template('course_attendance.html', course=course, attendance_records=attendance_records, today=today)

@app.route('/course/<int:course_id>/mark_attendance', methods=['POST'])
@login_required
@require_permission('manage_attendance')
def mark_attendance(course_id):
    course = Course.query.get_or_404(course_id)
    attendance_date = request.form.get('date')
    date_obj = datetime.strptime(attendance_date, '%Y-%m-%d').date()
    # Ensure the selected date falls on the course's configured weekday
    weekday_names = ['lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche']
    if date_obj.weekday() != course.day_of_week:
        flash(f"Veuillez sélectionner un {weekday_names[course.day_of_week]} pour ce cours.", 'error')
        return redirect(url_for('course_attendance', course_id=course_id))
    
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
@login_required
def export_products():
    try:
        from io import BytesIO
        from weasyprint import HTML, CSS
        from flask import render_template

        prods = Product.query.all()
        html = render_template('products_pdf.html', prods=prods)
        css = CSS(string='''
            body { font-family: Arial, sans-serif; font-size:12px; }
            h1 { font-size:18px; }
            table { width:100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 6px; }
        ''')
        buffer = BytesIO()
        HTML(string=html).write_pdf(target=buffer, stylesheets=[css])
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='products.pdf', mimetype='application/pdf')
    except Exception:
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
@login_required
def export_assignments():
    try:
        from io import BytesIO
        from weasyprint import HTML, CSS
        from flask import render_template

        assigns = Assignment.query.filter_by(date_returned=None).all()
        html = render_template('assignments_pdf.html', assigns=assigns)
        css = CSS(string='''
            body { font-family: Arial, sans-serif; font-size:12px; }
            h1 { font-size:18px; }
            table { width:100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 6px; }
        ''')
        buffer = BytesIO()
        HTML(string=html).write_pdf(target=buffer, stylesheets=[css])
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='assignments.pdf', mimetype='application/pdf')
    except Exception:
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
@login_required
def export_composites():
    try:
        from io import BytesIO
        from weasyprint import HTML, CSS
        from flask import render_template

        comps = CompositeProduct.query.all()
        html = render_template('composites_pdf.html', comps=comps)
        css = CSS(string='''
            body { font-family: Arial, sans-serif; font-size:12px; }
            h1 { font-size:18px; }
            table { width:100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 6px; }
        ''')
        buffer = BytesIO()
        HTML(string=html).write_pdf(target=buffer, stylesheets=[css])
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='composites.pdf', mimetype='application/pdf')
    except Exception:
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

@app.route('/export_archers')
@login_required
def export_archers():
    try:
        from io import BytesIO
        from weasyprint import HTML, CSS
        from flask import render_template

        archers = Archer.query.all()
        html = render_template('archers_pdf.html', archers=archers)
        css = CSS(string='''
            body { font-family: Arial, sans-serif; font-size:12px; }
            h1 { font-size:18px; }
            table { width:100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 6px; }
        ''')
        buffer = BytesIO()
        HTML(string=html).write_pdf(target=buffer, stylesheets=[css])
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='archers.pdf', mimetype='application/pdf')
    except Exception:
        from reportlab.pdfgen import canvas
        from io import BytesIO
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        archers = Archer.query.all()
        p.drawString(100, 800, "Liste des archérs")
        y = 780
        for archer in archers:
            archer_info = f"{archer.name} - License: {archer.license_number}"
            if archer.age:
                archer_info += f" - Age: {archer.age}"
            if archer.categorie:
                archer_info += f" - Catégorie: {archer.categorie}"
            p.drawString(100, y, archer_info)
            y -= 20
            if archer.bow_type:
                p.drawString(120, y, f"Type d'arc: {archer.bow_type}")
                y -= 15
            if y < 50:
                p.showPage()
                y = 800
        p.showPage()
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='archers.pdf', mimetype='application/pdf')

@app.route('/import_archers', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def import_archers():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            try:
                raw = file.stream.read()
                content = _decode_csv_bytes(raw)
                delim = _detect_csv_delimiter(content)
                lines = content.splitlines()
                if not lines:
                    return render_template(
                        'import_archers.html',
                        error='Le fichier CSV est vide ou mal formaté',
                    )
                header_reader = csv.reader(StringIO(lines[0]), delimiter=delim, quotechar='"')
                try:
                    header_cells = next(header_reader)
                except StopIteration:
                    return render_template(
                        'import_archers.html',
                        error='Le fichier CSV est vide ou mal formaté',
                    )
                fieldnames = _make_unique_csv_fieldnames(header_cells)
                body = '\n'.join(lines[1:])
                stream = StringIO(body, newline=None)
                csv_reader = csv.DictReader(
                    stream, fieldnames=fieldnames, delimiter=delim, quotechar='"'
                )

                imported = 0
                errors = []
                
                def clean_key(key):
                    if key is None:
                        return None
                    s = str(key).strip().strip('"').strip()
                    if s.startswith('\ufeff'):
                        s = s[1:].lstrip()
                    return s.strip()

                def normalize_header_for_match(s):
                    """Compare les en-têtes sans tenir compte des accents / casse / espaces."""
                    if s is None:
                        return ''
                    t = str(s).strip().strip('"')
                    if t.startswith('\ufeff'):
                        t = t[1:].lstrip()
                    t = unicodedata.normalize('NFD', t)
                    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
                    t = ' '.join(t.lower().split())
                    return t.strip(' :')

                # En-tête normalisé -> nom de colonne tel que DictReader le fournit
                norm_to_field = {}
                for f in fieldnames:
                    if f:
                        n = normalize_header_for_match(clean_key(f))
                        norm_to_field.setdefault(n, f)

                combined_nom_prenom_col = None
                for f in fieldnames:
                    if not f:
                        continue
                    if _header_is_nom_prenom_combine(
                        normalize_header_for_match(clean_key(f))
                    ):
                        combined_nom_prenom_col = f
                        break

                def cell_value(row_dict, field_name):
                    v = row_dict.get(field_name, '')
                    if v is None:
                        return ''
                    return v.strip() if isinstance(v, str) else str(v).strip()

                def find_column_fuzzy_name(row_dict, want_last_name=True):
                    """
                    Colonnes Nom / Prénom si le libellé export ne figure pas dans la liste fixe.
                    Ne pas utiliser « nom in prenom » (sinon on exclut « Prénom »).
                    """
                    bad = (
                        'responsable',
                        'legal',
                        'secondaire',
                        'structure',
                        'mail',
                        'telephone',
                        'tel',
                        'phone',
                    )
                    for key in row_dict:
                        nk = normalize_header_for_match(key)
                        if not nk or any(b in nk for b in bad):
                            continue
                        if want_last_name:
                            if 'prenom' in nk:
                                continue
                            if nk == 'nom' or nk.startswith('nom '):
                                return cell_value(row_dict, key)
                        else:
                            if nk == 'prenom' or nk.startswith('prenom'):
                                return cell_value(row_dict, key)
                    return ''

                def find_column(row_dict, *possible_names):
                    """Lit une cellule par libellés possibles d'en-tête."""
                    for name in possible_names:
                        n = normalize_header_for_match(name)
                        if n in norm_to_field:
                            return cell_value(row_dict, norm_to_field[n])
                        for key in row_dict:
                            if normalize_header_for_match(key) == n:
                                return cell_value(row_dict, key)
                    return ''

                _age_cat_re = re.compile(
                    r'U\s*\d{1,2}|S[ée]nior|Benjamin|Minime|Poussin|Cadet|Junior',
                    re.I,
                )

                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        license_number = find_column(
                            row,
                            'Code adhérent',
                            'Code adherent',
                            'Code',
                            'N° adhérent',
                            'Numero adherent',
                            'N°',
                            'Numéro',
                            'No',
                        ).strip()
                        if not license_number and fieldnames and fieldnames[0]:
                            v0 = cell_value(row, fieldnames[0]).strip()
                            if v0 and _IMPORT_LICENSE_RE.match(v0.replace(' ', '')):
                                license_number = v0
                        if not license_number and row:
                            k0 = list(row.keys())[0]
                            v0 = cell_value(row, k0).strip()
                            if v0 and _IMPORT_LICENSE_RE.match(v0.replace(' ', '')):
                                license_number = v0

                        first_name = find_column(
                            row,
                            'Prénom',
                            'Prenom',
                            'PRENOM',
                            'Prénom usuel',
                            'Prenom usuel',
                        ).strip()
                        if not first_name:
                            first_name = find_column_fuzzy_name(
                                row, want_last_name=False
                            ).strip()
                        last_name = find_column(
                            row,
                            'Nom',
                            'NOM',
                            'Nom de famille',
                            'Nom de naissance',
                            'Nom de l\'adhérent',
                            'Nom de l adhérent',
                            'Nom adhérent',
                            'Nom adherent',
                        ).strip()
                        if not last_name:
                            last_name = find_column_fuzzy_name(
                                row, want_last_name=True
                            ).strip()

                        if combined_nom_prenom_col:
                            combo = cell_value(row, combined_nom_prenom_col).strip()
                            if combo:
                                ln, fn = _split_nom_prenom_combined_cell(combo)
                                if ln:
                                    last_name = ln
                                if fn:
                                    first_name = fn

                        # Colonne « Nom » seule contenant « NOM Prénom » (sans colonne prénom)
                        if not (first_name or '').strip() and (last_name or '').strip():
                            ln_fix, fn_fix = _split_nom_prenom_combined_cell(last_name)
                            if fn_fix:
                                last_name = ln_fix
                                first_name = fn_fix

                        dob_str = find_column(
                            row,
                            'DDN',
                            'Date de naissance',
                            'Naissance',
                        ).strip()
                        categorie = find_column(
                            row,
                            'Catégorie âge sportif',
                            'Categorie age sportif',
                            'Catégorie',
                            'Categorie',
                            'Cat. sportive',
                        ).strip()
                        email_raw = find_column(
                            row,
                            'Adresse email',
                            'Adresse e-mail',
                            'Email',
                            'E-mail',
                            'Mail',
                            'Courriel',
                        ).strip()
                        email_val = _normalize_archer_email(email_raw)
                        if not categorie or not _age_cat_re.search(categorie):
                            for k in row:
                                nk = normalize_header_for_match(k).replace(' ', '')
                                if 'categorie' not in nk:
                                    continue
                                v = cell_value(row, k).strip()
                                if v and _age_cat_re.search(v):
                                    categorie = v
                                    break
                        
                        if not license_number or not last_name:
                            if not any(
                                cell_value(row, k).strip()
                                for k in row
                                if k is not None
                            ):
                                continue
                            errors.append(
                                f"Ligne {row_num}: Code adhérent et Nom sont obligatoires "
                                f"(reçu: code='{license_number}', nom='{last_name}')"
                            )
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
                        
                        # Vérifier si l'archer existe déjà
                        existing = Archer.query.filter_by(license_number=license_number).first()
                        if existing:
                            # Mettre à jour les données existantes
                            if first_name:
                                existing.first_name = first_name
                            if last_name:
                                existing.last_name = last_name
                            if age is not None:
                                existing.age = age
                            if categorie:
                                existing.categorie = categorie
                            if email_val is not None:
                                existing.email = email_val
                            imported += 1
                        else:
                            # Créer un nouvel archer
                            archer = Archer(
                                first_name=first_name,
                                last_name=last_name,
                                license_number=license_number,
                                email=email_val,
                                age=age,
                                categorie=categorie if categorie else None
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


@app.route('/import_composites', methods=['GET', 'POST'])
@login_required
@require_permission('edit')
def import_composites():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            try:
                raw = file.stream.read()
                content = _decode_csv_bytes(raw)
                delim = _detect_csv_delimiter(content)
                lines = content.splitlines()
                if not lines:
                    return render_template(
                        'import_composites.html',
                        error='Le fichier CSV est vide ou mal formaté',
                    )
                header_reader = csv.reader(StringIO(lines[0]), delimiter=delim, quotechar='"')
                try:
                    header_cells = next(header_reader)
                except StopIteration:
                    return render_template(
                        'import_composites.html',
                        error='Le fichier CSV est vide ou mal formaté',
                    )
                fieldnames = _make_unique_csv_fieldnames(header_cells)
                body = '\n'.join(lines[1:])
                stream = StringIO(body, newline=None)
                csv_reader = csv.DictReader(
                    stream, fieldnames=fieldnames, delimiter=delim, quotechar='"'
                )

                def normalize_header_for_match(s):
                    if s is None:
                        return ''
                    t = str(s).strip().strip('"')
                    if t.startswith('\ufeff'):
                        t = t[1:].lstrip()
                    t = unicodedata.normalize('NFD', t)
                    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
                    t = ' '.join(t.lower().split())
                    return t.strip(' :')

                norm_to_field = {}
                for f in fieldnames:
                    if f:
                        n = normalize_header_for_match(f)
                        norm_to_field.setdefault(n, f)

                def cell_value(row_dict, field_name):
                    v = row_dict.get(field_name, '')
                    if v is None:
                        return ''
                    return v.strip() if isinstance(v, str) else str(v).strip()

                def find_column(row_dict, *possible_names):
                    for name in possible_names:
                        n = normalize_header_for_match(name)
                        if n in norm_to_field:
                            return cell_value(row_dict, norm_to_field[n])
                        for key in row_dict:
                            if normalize_header_for_match(key) == n:
                                return cell_value(row_dict, key)
                    return ''

                imported = 0
                errors = []
                notices = []
                missing_export_arc_ids = 0

                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        if not any(cell_value(row, k).strip() for k in row if k is not None):
                            continue

                        id_raw = find_column(row, 'ID', 'Id').strip()
                        name = find_column(row, 'Nom', 'Name', 'Référence', 'Reference').strip()
                        type_raw = find_column(row, 'Type')
                        status_raw = find_column(row, 'Statut', 'Status')
                        comp_cell = find_column(row, 'Composants', 'Components', 'Pieces', 'Pièces')

                        if not name:
                            errors.append(
                                f"Ligne {row_num}: le nom de l'arc est obligatoire "
                                f"(reçu: « {name} »)"
                            )
                            continue

                        ctype = _normalize_composite_type_import(type_raw)
                        status = _normalize_composite_status_import(status_raw)

                        pairs = _split_composite_csv_component_cell(comp_cell)

                        cid = None
                        if id_raw:
                            try:
                                cid = int(id_raw)
                            except ValueError:
                                errors.append(f"Ligne {row_num}: ID arc invalide « {id_raw} »")
                                continue
                            if not CompositeProduct.query.get(cid):
                                missing_export_arc_ids += 1
                                cid = None

                        try:
                            with db.session.begin_nested():
                                new_products = []
                                seen_pid = set()
                                for brand, cat_name in pairs:
                                    (
                                        prod,
                                        created_p,
                                        created_c,
                                        ambiguous,
                                    ) = _get_or_create_product_for_composite_import(
                                        brand, cat_name
                                    )
                                    if not prod:
                                        raise ValueError(
                                            f"marque vide pour la catégorie « {cat_name} »"
                                        )
                                    if ambiguous:
                                        errors.append(
                                            f"Ligne {row_num}: plusieurs pièces pour "
                                            f"« {brand} ({cat_name}) », utilisation du produit "
                                            f"ID {prod.id}"
                                        )
                                    if created_c:
                                        notices.append(
                                            f"Ligne {row_num}: catégorie créée « {prod.category.name} »"
                                        )
                                    if created_p:
                                        notices.append(
                                            f"Ligne {row_num}: produit créé « {prod.brand} "
                                            f"({prod.category.name}) »"
                                        )
                                    pid = prod.id
                                    if pid not in seen_pid:
                                        seen_pid.add(pid)
                                        new_products.append(prod)

                                if cid is not None:
                                    comp = CompositeProduct.query.get(cid)
                                    old_components = [
                                        f"{p.brand} ({p.category.name})" for p in comp.components
                                    ]
                                    comp.name = name
                                    comp.type = ctype
                                    comp.status = status
                                    _sync_composite_components_from_products(
                                        comp, new_products, is_new=False
                                    )
                                    new_components = [
                                        f"{p.brand} ({p.category.name})" for p in comp.components
                                    ]
                                    if old_components != new_components:
                                        log_history(
                                            event_type='composite_change',
                                            entity_type='composite',
                                            entity_id=comp.id,
                                            summary=f"Composition modifiée (import CSV): {comp.name}",
                                            details={
                                                'before': old_components,
                                                'after': new_components,
                                            },
                                        )
                                else:
                                    comp = CompositeProduct(
                                        name=name, type=ctype, status=status
                                    )
                                    db.session.add(comp)
                                    db.session.flush()
                                    _sync_composite_components_from_products(
                                        comp, new_products, is_new=True
                                    )
                                    components = [
                                        f"{p.brand} ({p.category.name})"
                                        for p in comp.components
                                    ]
                                    log_history(
                                        event_type='composite_created',
                                        entity_type='composite',
                                        entity_id=comp.id,
                                        summary=f"Arc créé (import CSV): {comp.name}",
                                        details={
                                            'components': components,
                                            'type': comp.type,
                                            'status': comp.status,
                                        },
                                    )
                                imported += 1
                        except Exception as e:
                            errors.append(f"Ligne {row_num}: {str(e)}")
                    except Exception as e:
                        errors.append(f"Ligne {row_num}: {str(e)}")

                db.session.commit()
                if missing_export_arc_ids:
                    notices.insert(
                        0,
                        f"{missing_export_arc_ids} ligne(s) avaient un ID d’arc absent en base "
                        f"(export d’une autre base ou ancien) : de nouveaux arcs ont été créés, "
                        f"les IDs du fichier ont été ignorés.",
                    )
                return render_template(
                    'import_composites.html',
                    success=True,
                    imported=imported,
                    errors=errors,
                    notices=notices,
                )
            except Exception as e:
                return render_template(
                    'import_composites.html',
                    error=f"Erreur lors de la lecture du fichier: {str(e)}",
                )

    return render_template('import_composites.html')


# Routes d'export CSV
@app.route('/export_products_csv')
@login_required
@require_permission('view_equipment')
def export_products_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Catégorie', 'Marque', 'Modèle', 'Taille', 'Puissance', 'État', 'Lieu', 'Commentaires'])
    
    # Data
    prods = Product.query.join(Category).order_by(Category.name, Product.brand).all()
    for prod in prods:
        writer.writerow([
            prod.id,
            prod.category.name if prod.category else '',
            prod.brand or '',
            prod.model or '',
            prod.size or '',
            prod.power or '',
            prod.state or '',
            prod.location or '',
            prod.comments or ''
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'produits_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_archers_csv')
@login_required
def export_archers_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Prénom', 'Nom', 'Email', 'Numéro Licence', 'Âge', 'Catégorie', 'Type d\'arc', 'Personnel', 'Archer'])
    
    # Data
    archers = Archer.query.all()
    for archer in archers:
        writer.writerow([
            archer.id,
            archer.first_name or '',
            archer.last_name or '',
            archer.email or '',
            archer.license_number or '',
            archer.age or '',
            archer.categorie or '',
            archer.bow_type or '',
            'Oui' if getattr(archer, 'personal_equipment', None) else 'Non',
            'Oui' if getattr(archer, 'is_archer', None) else 'Non'
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'archers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_composites_csv')
@login_required
def export_composites_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Nom', 'Type', 'Statut', 'Composants'])
    
    # Data
    comps = CompositeProduct.query.all()
    for comp in comps:
        components_str = ' | '.join([f"{p.brand} ({p.category.name})" for p in comp.components])
        writer.writerow([
            comp.id,
            comp.name or '',
            comp.type or '',
            comp.status or '',
            components_str
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'arcs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_assignments_csv')
@login_required
@require_permission('view_assignments')
def export_assignments_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Archer', 'Arc', 'Date d\'assignation', 'Date de retour', 'Durée (jours)', 'Statut'])
    
    # Data
    assigns = Assignment.query.all()
    for ass in assigns:
        duration = ''
        status = 'Actif'
        if ass.date_returned:
            duration = (ass.date_returned - ass.date_assigned).days
            status = 'Retourné'
        else:
            duration = (datetime.now().date() - ass.date_assigned.date()).days if isinstance(ass.date_assigned, datetime) else ''
        
        writer.writerow([
            ass.id,
            f"{ass.archer.first_name} {ass.archer.last_name}" if ass.archer else '',
            ass.composite.name if ass.composite else '',
            ass.date_assigned.strftime('%d/%m/%Y') if ass.date_assigned else '',
            ass.date_returned.strftime('%d/%m/%Y') if ass.date_returned else '',
            duration,
            status
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'assignations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_categories_csv')
@login_required
@require_permission('view_equipment')
def export_categories_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Nom', 'Taille', 'Puissance', 'Modèle', 'Marque', 'Champs personnalisés', 'Nombre de produits'])
    
    # Data
    cats = Category.query.all()
    for cat in cats:
        writer.writerow([
            cat.id,
            cat.name or '',
            'Oui' if cat.has_size else 'Non',
            'Oui' if cat.has_power else 'Non',
            'Oui' if cat.has_model else 'Non',
            'Oui' if cat.has_brand else 'Non',
            cat.custom_fields or '',
            len(cat.products)
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'categories_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_courses_csv')
@login_required
@require_permission('view_courses')
def export_courses_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Nom', 'Date', 'Heure', 'Lieu', 'Nombre d\'archers inscrits', 'Capacité', 'Statut'])
    
    # Data
    courses = Course.query.all()
    for course in courses:
        writer.writerow([
            course.id,
            course.name or '',
            course.date.strftime('%d/%m/%Y') if hasattr(course, 'date') and course.date else '',
            course.time.strftime('%H:%M') if hasattr(course, 'time') and course.time else '',
            course.location or '',
            len(course.archers) if hasattr(course, 'archers') else 0,
            getattr(course, 'capacity', ''),
            'Actif' if not hasattr(course, 'cancelled') or not course.cancelled else 'Annulé'
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'cours_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/export_users_csv')
@login_required
@require_permission('admin')
def export_users_csv():
    from io import BytesIO
    output = StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow(['ID', 'Nom d\'utilisateur', 'Rôle'])
    
    # Data
    all_users = User.query.all()
    for user in all_users:
        writer.writerow([
            user.id,
            user.username or '',
            user.role or ''
        ])
    
    buffer = BytesIO(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'utilisateurs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

# Routes de gestion des utilisateurs (Admin only)
@app.route('/users')
@login_required
@require_permission('admin')
def users():
    all_users = User.query.all()
    roles = ['admin', 'responsable', 'lecteur', 'entraineur']
    return render_template('users.html', users=all_users, roles=roles)


def _safe_login_ip_filter(value):
    s = (value or '').strip()[:45]
    if not s or not re.match(r'^[\w.:%]+$', s):
        return None
    return s


@app.route('/login_history')
@login_required
@require_permission('admin')
def login_history():
    q = UserLoginEvent.query.order_by(UserLoginEvent.created_at.desc())
    user_id_arg = request.args.get('user_id', type=int)
    if user_id_arg:
        q = q.filter(UserLoginEvent.user_id == user_id_arg)
    ip_in_form = request.args.get('ip', '')
    ip_safe = _safe_login_ip_filter(ip_in_form)
    if ip_safe:
        q = q.filter(UserLoginEvent.ip_address.contains(ip_safe))
    page = request.args.get('page', default=1, type=int) or 1
    pagination = q.paginate(page=page, per_page=50, error_out=False)
    users_for_filter = User.query.order_by(User.username.asc()).all()
    return render_template(
        'login_history.html',
        pagination=pagination,
        users_for_filter=users_for_filter,
        filter_user_id=user_id_arg,
        filter_ip=ip_in_form.strip()[:45],
    )


@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@require_permission('admin')
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'responsable')
        
        # Vérifier que l'utilisateur n'existe pas déjà
        if User.query.filter_by(username=username).first():
            flash(f'Un utilisateur avec le nom "{username}" existe déjà.', 'error')
            return redirect(url_for('add_user'))
        
        # Créer le nouvel utilisateur
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        log_history(
            event_type='user_created',
            entity_type='user',
            entity_id=user.id,
            summary=f"Utilisateur créé: {username} (Rôle: {role})",
            details={'username': username, 'role': role}
        )
        db.session.commit()
        
        flash(f'Utilisateur "{username}" créé avec succès.', 'success')
        return redirect(url_for('users'))
    
    roles = ['admin', 'responsable', 'lecteur', 'entraineur']
    return render_template('add_user.html', roles=roles)

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@require_permission('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_role = request.form.get('role', user.role)
        password = request.form.get('password', '').strip()
        
        old_role = user.role
        user.role = new_role
        
        if password:
            user.set_password(password)
        
        db.session.commit()
        
        if old_role != new_role or password:
            changes = {}
            if old_role != new_role:
                changes['role'] = {'from': old_role, 'to': new_role}
            if password:
                changes['password'] = 'Mot de passe changé'
            
            log_history(
                event_type='user_updated',
                entity_type='user',
                entity_id=user.id,
                summary=f"Utilisateur modifié: {user.username}",
                details={'changes': changes}
            )
            db.session.commit()
        
        flash(f'Utilisateur "{user.username}" modifié avec succès.', 'success')
        return redirect(url_for('users'))
    
    roles = ['admin', 'responsable', 'lecteur', 'entraineur']
    return render_template('edit_user.html', user=user, roles=roles)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@require_permission('admin')
def delete_user(user_id):
    # Empêcher la suppression du dernier admin
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte.', 'error')
        return redirect(url_for('users'))
    
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('Il doit y avoir au moins un administrateur.', 'error')
            return redirect(url_for('users'))
    
    username = user.username
    db.session.delete(user)
    
    log_history(
        event_type='user_deleted',
        entity_type='user',
        entity_id=user.id,
        summary=f"Utilisateur supprimé: {username}",
        details={'username': username}
    )
    
    db.session.commit()
    flash(f'Utilisateur "{username}" supprimé avec succès.', 'success')
    return redirect(url_for('users'))


@app.cli.command('reset-admin-password')
@click.option('--username', '-u', default='admin', show_default=True, help='Compte à mettre à jour.')
@click.option(
    '--password',
    '-p',
    default=None,
    help='Nouveau mot de passe (évite la saisie interactive ; reste visible dans l’historique du shell).',
)
def reset_admin_password_command(username, password):
    """Réinitialise le mot de passe d’un utilisateur (ex. admin oublié)."""
    import getpass

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            click.echo(f'Utilisateur « {username} » introuvable.', err=True)
            raise SystemExit(1)
        if password is None:
            password = getpass.getpass('Nouveau mot de passe : ')
            confirm = getpass.getpass('Confirmation : ')
            if password != confirm:
                click.echo('Les mots de passe ne correspondent pas.', err=True)
                raise SystemExit(1)
        if not password:
            click.echo('Mot de passe vide.', err=True)
            raise SystemExit(1)
        user.set_password(password)
        db.session.commit()
        click.echo(f'Mot de passe mis à jour pour « {username} ».')


if __name__ == '__main__':
    import os
    # Default port handling: respect $PORT if set, otherwise
    # run on port 80 when executed as root/admin, else 5000.
    port_env = os.environ.get('PORT')
    is_root = False
    # Unix-like: check geteuid
    if hasattr(os, 'geteuid'):
        try:
            is_root = (os.geteuid() == 0)
        except Exception:
            is_root = False
    else:
        # Windows: try to detect admin privileges
        try:
            import ctypes
            is_root = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_root = False

    if port_env:
        try:
            port = int(port_env)
        except Exception:
            port = 5000
    else:
        port = 80 if is_root else 5000

    debug = os.environ.get('FLASK_DEBUG', '1') in ('1', 'true', 'True')
    app.run(debug=debug, port=port, host='0.0.0.0')