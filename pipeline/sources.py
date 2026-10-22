"""The registry of published lists: one entry per source, the adapter that reads it and the file it produces."""
import pipeline.adapter_bee as AE
import pipeline.adapter_bis as AB
import pipeline.adapter_crs as AC
import pipeline.adapter_pdf as AP

BIS_BASE = 'https://www.bis.gov.in'

# id -> raw/<id>/<date>/<stem>_<date>.<ext>; `lang`: bis.gov.in is asked for ?lang=en
LISTS = [
    dict(id='bis-scheme1', out='data/bis/isi_qco.csv', parse=AB.parse_scheme1, stem='www.bis.gov.in_scheme-1', ext='html', lang=True,
         url=BIS_BASE + '/product-certification/products-under-compulsory-certification/scheme-1/'),
    dict(id='bis-scheme2', out='data/bis/scheme_ii_other.csv', parse=AB.parse_scheme2_other, stem='www.bis.gov.in_scheme-ii', ext='html', lang=True,
         url=BIS_BASE + '/product-certification/products-under-compulsory-certification/scheme-ii-registration-scheme/'),
    dict(id='crs', out='data/bis/crs.csv', parse=AC.parse_crs, stem='crsbis_products-bis', ext='html', lang=False,
         url='https://www.crsbis.in/BIS/products-bis.do', extra_cols=['enforcement_date']),
    dict(id='bis-scheme4', out='data/bis/scheme_iv.csv', parse=AB.parse_scheme4, stem='www.bis.gov.in_scheme-4', ext='html', lang=True,
         url=BIS_BASE + '/product-certification/products-under-compulsory-certification/scheme-4/'),
    dict(id='bis-schemex', out='data/bis/scheme_x.csv', parse=AB.parse_scheme_x, stem='www.bis.gov.in_scheme-x', ext='html', lang=True,
         url=BIS_BASE + '/products-under-compulsory-certification-scheme-x/'),
    dict(id='bis-upcoming', out='data/bis/qco_upcoming.csv', parse=AB.parse_upcoming, stem='www.bis.gov.in_upcoming-qcos', ext='html', lang=True,
         url=BIS_BASE + '/upcoming-qcos-notified-and-due-for-implementation/'),
    dict(id='bis-option2', out='data/bis/option2.csv', parse=AP.parse_simplified, stem='www.bis.gov.in_simplified-2024', ext='pdf', lang=False,
         url=BIS_BASE + '/wp-content/uploads/2024/11/List-of-Products-Under-Simplified-Procedure.pdf'),
    dict(id='tec-mtcte', out='data/tec/mtcte.csv', parse=AP.parse_mtcte, stem='mtcte.tec.gov.in_ProductsList', ext='pdf', lang=False,
         url='https://mtcte.tec.gov.in/filedownload?name=downloadDocument_ProductsList.pdf'),
]

BEE = dict(
    mandatory=dict(id='bee-mandatory', url='https://www.beestarlabel.com/Home/EquipmentSchemes?type=M', stem='www.beestarlabel.com_EquipmentSchemes-M', ext='html'),
    voluntary=dict(id='bee-voluntary', url='https://www.beestarlabel.com/Home/EquipmentSchemes?type=V', stem='www.beestarlabel.com_EquipmentSchemes-V', ext='html'),
    out_mandatory='data/bee/mandatory.csv', out_voluntary='data/bee/voluntary.csv', parse=AE.parse_bee)

ITCHS_DIR = 'data/itchs/2022'
ITCHS_RAW = 'raw/dgft-itchs-2022'
QCO_DIR = 'data/qco'


def source_urls():
    """[(id, url)] of every page the refresh reads from the web, in the form it is fetched (lang=en where the refresh asks for it)."""
    sep = lambda u: u + ('&' if '?' in u else '?') + 'lang=en'  # noqa: E731
    out = [(s['id'], sep(s['url']) if s['lang'] else s['url']) for s in LISTS]
    out += [(BEE[k]['id'], BEE[k]['url']) for k in ('mandatory', 'voluntary')]
    return out
