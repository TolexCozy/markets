from django.contrib import admin
from events.models import Contact, Product, Orders, OrderUpdate, Category, ProductImage

admin.site.register(Contact)
admin.site.register(Product)
admin.site.register(Category)
admin.site.register(ProductImage)

@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    # Removed 'timestamp' since it caused an error. 
    # If you have a date field, replace 'paymentstatus' with that name.
    list_display = ('order_id', 'name', 'email', 'amountpaid', 'paymentstatus')
    list_filter = ('paymentstatus',)
    search_fields = ('name', 'email', 'order_id')

@admin.register(OrderUpdate)
class OrderUpdateAdmin(admin.ModelAdmin):
    # Changed 'order_id' to 'Order_id' based on your previous view code
    list_display = ('Order_id', 'update_desc')