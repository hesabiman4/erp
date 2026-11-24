from .api import Boundary, response
from .counter_sales import availability, repeat_sale, configure
from django.core.exceptions import ValidationError


class CounterSalesAPI(Boundary):
    def get(self, request, section):
        ctx = self.ctx(request)
        if section == 'availability':
            params = dict(request.query_params.items())
            warehouse = params.get('warehouse')
            location = request.headers.get('X-Location-ID')
            if warehouse and location:
                from .core import get_warehouse
                from .models import Location
                from .core import get_obj
                if get_warehouse(ctx, warehouse).location_id != get_obj(ctx, Location, location).id:
                    raise ValidationError('Warehouse does not belong to the selected location.')
            return response(availability(ctx, params))
        if section == 'repeat':
            value = repeat_sale(ctx, request.query_params.get('invoice'))
            location = request.headers.get('X-Location-ID')
            if location:
                from .core import get_obj, get_warehouse
                from .models import Location
                if get_warehouse(ctx, value['warehouse']).location_id != get_obj(ctx, Location, location).id:
                    raise ValidationError('Original sale is outside the selected location.')
            return response(value)
        raise ValidationError('Unknown counter-sale section.')

    def post(self, request, section):
        if section != 'shortcuts': raise ValidationError('Only thickness shortcuts can be configured here.')
        return response(configure(self.ctx(request), request.data))
