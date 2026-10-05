from django.urls import path
from .import views

app_name = 'events'

urlpatterns = [
    path('', views.base, name='base'),
    path('menuf/', views.menuf, name='menuf'),
    path('menu/', views.menu_view, name='menu_view'),
    path('contact', views.contact,name="contact"),
    path('contact/', views.contact_us, name='contact_us'),
    path('about', views.about,name="about"),
    path('profile', views.profile,name="profile"),
    path('checkout/', views.checkout,name="checkout"),
    path('handlerequest/', views.handlerequest,name="Handlerequest"),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('thank-you/', views.thanks_page, name='thanks'),
    path('submit-feedback/', views.submit_feedback, name='submit_feedback'),
]
