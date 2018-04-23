# -*- coding: utf-8 -*-

from openerp import http
from openerp import release
from openerp.http import request
from openerp import SUPERUSER_ID, fields
from werkzeug.wrappers import BaseResponse as Response
from openerp.tools.translate import _
from datetime import datetime

import re
import os
import json
import pytz
import logging
_logger = logging.getLogger(__name__)


class SequraController(http.Controller):

    @http.route(['/sequra/shop/confirmation'], type='http', auth="public", website=True)
    def sequra_payment_confirmation(self, **post):
        cr, uid, context = request.cr, request.uid, request.context

        # clean context and session, then redirect to the confirmation page
        request.website.sale_reset(context=context)
        return request.redirect('/shop/confirmation')

    @http.route('/checkout/sequra-ipn', type='http', auth='none', methods=['POST'])
    def checkout_sequra_ipn(self, **post):
        _logger.info("********Sequra IPN ***********")
        _logger.info("***************/checkout/sequra-ipn *******************")
        _logger.info(post)
        _logger.info("*******************************************************")

        cr, uid, pool = request.cr, SUPERUSER_ID, request.registry

        order_ref = post.get('order_ref') # sequra reference
        order_ref_1 = post.get('order_ref_1') #odoo reference

        if order_ref and order_ref_1:
            order_obj = pool['sale.order']
            order = order_obj.search(cr, uid, [('sequra_location', 'like', '%'+order_ref)])
            if len(order):
                order = order_obj.browse(cr, uid, order[0])
                if order_ref_1 == order.name:
                    tx_obj = pool['payment.transaction']
                    tx_id = tx_obj.search(cr, uid, [('reference', '=', order_ref_1)])

                    if tx_id:
                        tx = tx_obj.browse(cr, uid, tx_id)

                        post = {
                            'merchant_id': tx.acquirer_id.sequra_merchant,
                            'shipping_method': order.shipping_method,
                        }

                        data = self._get_data_json(post, order, 'confirmed')
                        endpoint = order.sequra_location
                        response = tx.acquirer_id.request(endpoint, method='PUT', data=data)

                        values = {
                            'sequra_conf_resp_status_code': response.status_code,
                            'sequra_conf_resp_reason': response.reason
                        }
                        if 299 >= response.status_code >= 200:
                            values.update({
                                'state': 'done',
                                'order_sequra_ref': order_ref,
                            })
                            tx.write(values)
                            if tx.acquirer_id.send_quotation:
                                email_act = tx.sale_order_id.action_quotation_send()
                                # send the email
                                if email_act and email_act.get('context'):
                                    tx.send_mail(email_act['context'])

                            return Response('OK', status=200)
                        elif response.status_code == 409:
                            _logger.info("***************/checkout/sequra-ipn *******************")
                            _logger.info("Cart has changed")
                            return Response('Conflict', status=409)
                        else:
                            _logger.info("***************/checkout/sequra-ipn *******************")
                            _logger.info("Error found in sequra response with status code %s" % response.status_code)
                            return Response(response.reason, status=response.status_code)
                else:
                    _logger.info("***************/checkout/sequra-ipn *******************")
                    _logger.info("order_ref_1 = %s no found in odoo" % order_ref_1)
                    return Response('Not Found', status=404)

        else:
            _logger.info("***************/checkout/sequra-ipn *******************")
            _logger.info("********One or either order reference empty ***********")
            _logger.info("order_ref = %s" % order_ref)
            _logger.info("order_ref_1 = %s" % order_ref_1)

    @http.route('/payment/sequra', type='http', auth='public', methods=['POST'], website=True)
    def payment_sequra(self, **post):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.registry

        acquirer_obj = pool['payment.acquirer']
        acquirer_id = acquirer_obj.browse(cr, SUPERUSER_ID, int(post.get('acquirer_id', -1)))

        r = self.start_solicitation(acquirer_id, post)
        if r.status_code == 204:
            location = r.headers.get('Location')
            method_payment = post.get('payment_method')
            r = self.fetch_id_form(acquirer_id, location, method_payment)
            if r.status_code == 200:
                order = request.website.sale_get_order()
                order.write({
                    'sequra_location': location,
                    'shipping_method': post.get('shipping_method')
                })
                values = {
                    'partner': order.partner_id.id,
                    'order': order,
                    'errors': [],
                    'iframe': r.content
                }
                self.render_payment_acquirer(order, values)
                return request.website.render("payment_sequra.payment", values)
        json = r.json()
        error = json and len(json['errors']) and json['errors'][0] or ''
        return request.website.render("payment_sequra.500", {'error': error})

    def start_solicitation(self, acquirer_id,  post):
        post.update({
            'merchant_id': acquirer_id.sequra_merchant
        })
        data = self._get_data_json(post)
        endpoint = '/orders'
        r = acquirer_id.request(endpoint, data=data)
        return r

    def fetch_id_form(self, acquirer_id, location, payment_method=None):
        headers = {
            'Accept': 'text/html'
        }
        endpoint = '%s/form_v2' % location
        if payment_method:
            endpoint += '?product=%s' % payment_method
        r = acquirer_id.request(endpoint, 'GET', headers=headers)
        return r

    def _get_customer_data(self, partner_id, order_id):
        cr, uid, pool = request.cr, SUPERUSER_ID, request.registry

        order_obj = pool['sale.order']
        order_ids = order_obj.search(cr, uid, [
            ('partner_id', '=', partner_id.id),
            ('id', '!=', order_id)
        ], limit=10, order='create_date desc')

        order_ids = order_obj.browse(cr, SUPERUSER_ID, order_ids)

        previous_orders = [{
            'created_at': fields.Datetime.from_string(o.create_date).replace(tzinfo=pytz.timezone(o.partner_id.tz or 'Europe/Madrid'), microsecond=0).isoformat(),
            'amount': int(round(o.amount_total * 100, 2)),
            'currency': o.currency_id.name
        } for o in order_ids]
        customer = self._get_address(partner_id)
        if "HTTP_X_FORWARDED_FOR" in request.httprequest.environ:
        # Virtual host        
            ip = request.httprequest.environ["HTTP_X_FORWARDED_FOR"]
        elif "HTTP_HOST" in request.httprequest.environ:
            # Non-virtualhost
            ip = request.httprequest.environ["REMOTE_ADDR"]
        customer['email'] =  partner_id.email or ""
        customer['language_code'] = "es-ES"
        customer['ref'] = partner_id.id
        customer['company'] = partner_id.company_id.name or ""
        customer['logged_in'] = 'unknown'
        customer['ip_number'] = ip
        customer['user_agent'] = request.httprequest.environ["HTTP_USER_AGENT"]
        customer['vat_number'] = partner_id.company_id.vat or ""
        customer['previous_orders'] = previous_orders
        return customer

    def _get_address(self, partner_id):
        def _partner_split_name(partner_name):
            return [' '.join(partner_name.split()[:-1]), ' '.join(partner_name.split()[-1:])]

        return {
            "given_names": _partner_split_name(partner_id.name)[1],
            "surnames": _partner_split_name(partner_id.name)[0],
            "company": partner_id.company_id.name or "",
            "address_line_1": partner_id.street or "",
            "address_line_2": partner_id.street2 or "",
            "postal_code": partner_id.zip or "",
            "city": partner_id.city or "",
            "country_code": partner_id.country_id.code or "",
            "phone": partner_id.phone or "",
            "mobile_phone": partner_id.mobile or "",
            "nin": partner_id.vat[2:] or ""
        }

    def _get_items(self, order_id, shipping_name):
        items = []
        for sol in order_id.order_line:
            price_subtotal = sol.price_subtotal
            total_without_tax = int(round(price_subtotal * 100, 2))
            price_without_tax = int(round((price_subtotal / sol.product_uom_qty) * 100, 2))

            tax = order_id._amount_line_tax(sol)

            total_with_tax = int(round((price_subtotal + tax) * 100, 2))
            price_with_tax = int(round(((price_subtotal + tax)/sol.product_uom_qty) * 100, 2))

            if order_id.carrier_id.name != sol.name:
                item = {
                    "reference": str(sol.product_id.id),
                    "name": sol.name,
                    "tax_rate": 0,
                    "quantity": int(sol.product_uom_qty),
                    "price_with_tax": price_with_tax,
                    "total_with_tax": total_with_tax,
                    "price_without_tax": price_without_tax,
                    "total_without_tax": total_without_tax,
                    "downloadable": False,
                    "supplier": "",
                    "product_id": sol.product_id.id,
                    "url": ""
                }
            else:
                item = {
                    "type": "handling",
                    "reference": "Costes de envío",
                    "name": shipping_name,
                    "tax_rate": 0,
                    "total_with_tax": total_with_tax,
                    "total_without_tax": total_without_tax,
                }

            items.append(item)

        return items

    def _get_data_json(self, post, aorder=None, state=''):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.registry

        base_url = pool['ir.config_parameter'].get_param(cr, SUPERUSER_ID, 'web.base.url')

        notify_url = '%s/checkout/sequra-ipn' % base_url

        order = aorder or request.website.sale_get_order()

        return_url = '%s/sequra/shop/confirmation?payment_method=sq-SQ_PRODUCT_CODE' % (
        base_url)  # '%s/checkout/sequra-confirmed' % base_url

        partner_id = order.partner_id
        partner_invoice_id = order.partner_invoice_id
        partner_shipping_id = order.partner_shipping_id

        shipping_method = post.get('shipping_method').split('-')

        model_data_obj = pool['ir.model.data']
        company_obj = pool['res.company']
        company_id = model_data_obj.xmlid_to_res_id(cr, SUPERUSER_ID, 'base.main_company')
        company_id = company_obj.browse(cr, SUPERUSER_ID, company_id)
        currency = company_id.currency_id.name

        merchant_id = post.get('merchant_id')

        merchant_values = {
            "id": merchant_id,
            "notify_url": notify_url,
            "return_url": return_url,
            "notification_parameters": {
                "test": 'test'
            }
        }

        return json.dumps(
            {
                "order": {
                    "state": state,
                    "merchant": merchant_values,
                    "merchant_reference": {
                        "order_ref_1": order.name
                    },
                    "cart": {
                        "cart_ref": order.name,
                        "currency": currency or "EUR",
                        "gift": False,
                        "items": self._get_items(order, shipping_method[0]),
                        "order_total_with_tax": int(round((order.amount_total) * 100, 2))
                    },
                    "delivery_address": self._get_address(partner_shipping_id),
                    "invoice_address": self._get_address(partner_invoice_id),
                    "customer": self._get_customer_data(partner_id, order.id),
                    "delivery_method": {
                        "name": shipping_method[0],
                        "days": shipping_method[1]
                    },
                    "gui": {
                        "layout": "desktop"
                    },
                    "platform": {
                        "name": "Odoo",
                        "version": release.version,
                        "uname": " ".join(os.uname()),
                        "db_name": "postgresql",
                        "db_version": "9.4"
                    }
                }
            }
        )

    def render_payment_acquirer(self, order, values):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.registry

        shipping_partner_id = False
        if order:
            if order.partner_shipping_id.id:
                shipping_partner_id = order.partner_shipping_id.id
            else:
                shipping_partner_id = order.partner_invoice_id.id

        payment_obj = pool.get('payment.acquirer')
        acquirer_ids = payment_obj.search(cr, SUPERUSER_ID,
                                          [('website_published', '=', True), ('company_id', '=', order.company_id.id)],
                                          context=context)
        values['acquirers'] = list(payment_obj.browse(cr, uid, acquirer_ids, context=context))
        render_ctx = dict(context, submit_class='btn btn-primary', submit_txt=_('Pay Now'))
        for acquirer in values['acquirers']:
            acquirer.button = payment_obj.render(
                cr, SUPERUSER_ID, acquirer.id,
                order.name,
                order.amount_total,
                order.pricelist_id.currency_id.id,
                partner_id=shipping_partner_id,
                tx_values={
                    'return_url': '/shop/payment/validate',
                },
                context=render_ctx)






