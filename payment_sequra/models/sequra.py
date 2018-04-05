# -*- coding: utf-'8' "-*-"

import logging
import requests
# import hashlib

from openerp import models, fields, api, _

_logger = logging.getLogger(__name__)


class AcquirerSequra(models.Model):
    _inherit = 'payment.acquirer'

    def _get_sequra_urls(self):
        """ Sequra URLS """
        if self.environment == 'test':
            return 'https://sandbox.sequrapi.com'
        return 'https://live.sequrapi.com'

    @api.model
    def _get_providers(self):
        providers = super(AcquirerSequra, self)._get_providers()
        providers.append(['sequra', 'SeQura'])
        return providers

    def request(self, endpoint, method='POST', data='{}', headers=None):
        if not headers:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        url = endpoint.find('http') == -1 and self._get_sequra_urls() + endpoint or endpoint
        if method == 'POST':
            return requests.post(
                url,
                auth=(self.sequra_user, self.sequra_pass),
                data=data,
                headers=headers
            )
        elif method == 'GET':
            return requests.get(
                url,
                auth=(self.sequra_user, self.sequra_pass),
                headers=headers
            )
        else:
            return requests.put(
                url,
                auth=(self.sequra_user, self.sequra_pass),
                verify=False,
                data=data,
                headers=headers
            )

    sequra_user = fields.Char('Sequra User')
    sequra_pass = fields.Char('Sequra Password')
    sequra_merchant = fields.Char('Sequra Merchant')


class TxSequra(models.Model):
    _inherit = 'payment.transaction'

    order_sequra_ref = fields.Char('Sequra order reference')
    provider = fields.Selection(related='acquirer_id.provider')

    sequra_conf_resp_status_code = fields.Char('Confirmation Response Status Code')
    sequra_conf_resp_reason = fields.Text('Confirmation Response Reason')

    def send_mail(self, email_ctx):
        composer_values = {}
        template = self.env.ref('sale.email_template_edi_sale', False)
        if not template:
            return True
        email_ctx['default_template_id'] = template.id
        composer_id = self.env['mail.compose.message'].with_context(
            email_ctx).create(composer_values)
        composer_id.with_context(email_ctx).send_mail()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sequra_location = fields.Text('Sequra Location')
    order_sequra_ref = fields.Char('Sequra order reference', compute='_compute_sequra_ref')
    shipping_method = fields.Char('Sequra Shipping Method')
    # order_id_sha1 = fields.Char('Order Id Sha1', compute='_compute_order_id_sha1', store=True)

    @api.one
    @api.depends('sequra_location')
    def _compute_sequra_ref(self):
        s_location = self.sequra_location and self.sequra_location.split('/') or None
        self.order_sequra_ref = s_location and s_location[len(s_location) - 1] or ''

