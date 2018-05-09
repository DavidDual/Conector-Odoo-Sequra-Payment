from openerp import api, tools, SUPERUSER_ID
from openerp.osv import osv, fields, expression

class product_template(osv.osv):
    _inherit = 'product.template'
    _columns = {
        'ends_in' : fields.char('Service end date',default='P6M',select=True, required=True, translate=False),
    }