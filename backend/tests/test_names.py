from app.names import format_person_name, given_name, name_sort_key, split_person_name


def test_format_person_name():
    assert format_person_name("Anna PU Berg") == "PU Berg, Anna"
    assert format_person_name("Berg, Anna PU") == "PU Berg, Anna"
    assert format_person_name("Max Mustermann") == "Mustermann, Max"
    assert format_person_name("Mustermann, Max") == "Mustermann, Max"
    assert format_person_name("Administrator") == "Administrator"
    assert format_person_name("") == ""


def test_split_keeps_prefix_with_the_last_name():
    assert split_person_name("Anna NL Sommer") == ("Anna", "NL Sommer")
    assert split_person_name("Sommer, Anna NL") == ("Anna", "NL Sommer")


def test_given_name_is_the_first_word():
    assert given_name("Max Mustermann") == "Max"
    assert given_name("Mustermann, Max Peter") == "Max"
    assert given_name("Personal") == "Personal"


def test_sort_key_uses_last_name():
    ordered = sorted(["Zoe Abend", "Anna Morgen", "Ben Abend", "Anna PU Berg"], key=name_sort_key)
    assert [format_person_name(name) for name in ordered] == [
        "Abend, Ben",
        "Abend, Zoe",
        "Morgen, Anna",
        "PU Berg, Anna",
    ]
