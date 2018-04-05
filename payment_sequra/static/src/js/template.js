// this .js is no used for now
odoo.define('payment_sequra', function (require) {
    "use strict";
    var ajax = require('web.ajax');

    $(".oe_sequra_payment_form").on("submit", function (e) {
        var self = this;
        e.preventDefault();
        var $oe_sequra_payment_form = $(this);
        var formData = new FormData($oe_sequra_payment_form[0]);
        $.ajax({
            url: '/payment/sequra',
            type: "POST",
            dataType: "html",
            data: formData,
            cache: false,
            contentType: false,
            processData: false
        }).done(function(res){
            var response = JSON.parse(res);
        });
    });
    
});

