from parsers.bca     import extract_bca_mutation
from parsers.cimb    import extract_cimb_mutation, extract_cimb_v2_mutation, extract_cimb_v3_mutation
from parsers.bri     import extract_bri_mutation
from parsers.danamon import extract_danamon_mutation
from parsers.bni     import extract_bni_mutation
from parsers.mandiri import extract_mandiri_mutation, extract_mandiri_rek_koran

PARSER_REGISTRY: dict = {
    "BCA":        lambda path, pw, year, **_: extract_bca_mutation(path, year, pw),
    "CIMB":       lambda path, pw, **_:       extract_cimb_mutation(path, pw),
    "CIMB_V2":    lambda path, pw, **_:       extract_cimb_v2_mutation(path, pw),
    "CIMB_V3":    lambda path, pw, **_:       extract_cimb_v3_mutation(path, pw),
    "BRI":        lambda path, pw, **_:       extract_bri_mutation(path, pw),
    "DANAMON":    lambda path, pw, **_:       extract_danamon_mutation(path, pw),
    "BNI":        lambda path, pw, **_:       extract_bni_mutation(path, pw),
    "MANDIRI":    lambda path, pw, **_:       extract_mandiri_mutation(path, pw),
    "MANDIRI_RK": lambda path, pw, **_:       extract_mandiri_rek_koran(path, pw),
}
