"""Gatunki pupili — stałe.

Osiem gatunków inspirowanych maskotkami ATEEZ, własna grafika (rig SVG w etapie 4;
lustro tej listy powstanie w static/js/pet/species.js). Zmiana nazwy = edycja tej stałej,
celowo bez UI.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Species:
    slug: str
    name: str
    palette: dict   # base, light, dark, cheek — kolory HEX
    extras: tuple = ()  # cechy rigu: uszy, ogon, dodatki


SPECIES = (
    Species('wiewiorka', 'Wiewiórka',
            {'base': '#F4A261', 'light': '#FBE3C9', 'dark': '#C8732F', 'cheek': '#F7B7A3'},
            ('stripes', 'bushy_tail')),
    Species('kroliczek', 'Króliczek',
            {'base': '#F7B6D2', 'light': '#FDE4EF', 'dark': '#E58BB5', 'cheek': '#F48FB1'},
            ('long_ears', 'sparkles')),
    Species('szczeniak', 'Szczeniak',
            {'base': '#F6E3B4', 'light': '#FFF6DE', 'dark': '#D9BE7A', 'cheek': '#F5B5A1'},
            ('floppy_ears', 'fringe')),
    Species('piesek', 'Piesek',
            {'base': '#FFFFFF', 'light': '#FFFFFF', 'dark': '#D9D9D9', 'cheek': '#F8BBD0'},
            ('long_floppy_ears',)),
    Species('kotek', 'Kotek',
            {'base': '#C9C3E6', 'light': '#E8E4F5', 'dark': '#9D94C9', 'cheek': '#F3A6C4'},
            ('pointy_ears', 'white_muzzle')),
    Species('kurczaczek', 'Kurczaczek',
            {'base': '#FDE68A', 'light': '#FFF4C2', 'dark': '#E3C44A', 'cheek': '#F9B27A'},
            ('beak', 'crest')),
    Species('czarny-kotek', 'Czarny Kotek',
            {'base': '#2B2B2B', 'light': '#4A4A4A', 'dark': '#111111', 'cheek': '#6B4A4A'},
            ('pointy_ears', 'collar_bell')),
    Species('mis', 'Miś',
            {'base': '#B5835A', 'light': '#E3C3A0', 'dark': '#8A5F3C', 'cheek': '#E9A087'},
            ('round_ears', 'leaf')),
)

SPECIES_BY_SLUG = {s.slug: s for s in SPECIES}
SPECIES_SLUGS = tuple(s.slug for s in SPECIES)
