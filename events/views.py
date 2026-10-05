import email
import re

from django.shortcuts import render

from django.views.decorators.csrf import csrf_exempt

from django.contrib import messages

import logging
import requests

from django.conf import settings

from .models import Contact

from django.shortcuts import render, redirect 


import logging
from django.db import transaction
from django.db.models import Q

from django.urls import reverse

logger = logging.getLogger(__name__)

from .models import Orders, OrderUpdate 

from django.shortcuts import render, get_object_or_404

from django.core.mail import send_mail

from .models import Feedback

import json
from decimal import Decimal, ROUND_HALF_UP

from .models import Product, Category

import time


# Create your views here.

def base(request):
    return render(request, 'base.html', {'sitename': 'NiceRestaurant'})

def starter(request):
    return render(request, 'starter.html')

def menuf(request):
    return render(request, 'menuf.html')


def contact(request):
    if request.method=="POST":
        name=request.POST.get("name")
        email=request.POST.get("email")
        desc=request.POST.get("desc")
        pnumber=request.POST.get("pnumber")
        myquery=Contact(name=name, email=email, desc=desc, phonenumber=pnumber)
        myquery.save()
        messages.info(request, "we will get back to you soon...")
        return render(request, "contact.html")

    return render(request, "contact.html")

def about(request):
    return render(request, "about.html")





logger = logging.getLogger(__name__)

def checkout(request):
    if not request.user.is_authenticated:
        messages.warning(request, "Login & Try Again")
        return redirect(f"{reverse('account:handlelogin')}?next={reverse('events:checkout')}")
    
    # 1. Shared Logic: Calculate Totals from Session Cart
    cart = request.session.get('cart', {})
    if not cart and request.method == "POST":
        messages.error(request, "Your cart is empty.")
        return redirect('events:cart_detail')

    subtotal = Decimal('0.00')
    cart_items = []
    item_count = 0
    serializable_cart = {}

    for item_id, item in cart.items():
        price = Decimal(str(item.get('price', 0)))
        quantity = item.get('quantity', 0)
        item_total = price * quantity
        
        # Prepare for Template Display
        item['total_price'] = item_total
        cart_items.append(item)
        
        # Prepare for JSON storage
        serializable_cart[item_id] = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in item.items()
        }
        
        subtotal += item_total
        item_count += quantity

    tax = (subtotal * Decimal('0.03')).quantize(Decimal('0.01'))
    total = subtotal + tax

    # 2. Handle Form Submission (POST)
    if request.method == "POST":
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        address1 = request.POST.get('address', '')
        address2 = request.POST.get('address2', '')
        city = request.POST.get('city', '')
        state = request.POST.get('state', '')
        zip_code = request.POST.get('zip', '')
        phone = request.POST.get('phone', '')

        # Validate checkout fields
        errors = []

        def count_words(value):
            return len(value.strip().split()) if value.strip() else 0

        if not phone:
            errors.append('Phone number is required.')
        else:
            phone = phone.strip()
            if ' ' in phone:
                errors.append('Phone number must not contain spaces.')
            elif not re.fullmatch(r"\+(?:234\d{10,11}|1\d{10})", phone):
                errors.append('Phone number must start with +234 or +1 and contain only digits with the correct length.')

        for field_value, field_name in [
            (address1, 'Address'),
            (city, 'City'),
            (state, 'State')
        ]:
            word_count = count_words(field_value)
            if word_count < 5:
                errors.append(f'{field_name} must contain at least 5 words.')
            elif word_count > 30:
                errors.append(f'{field_name} must contain fewer than 30 words.')

        if not zip_code:
            errors.append('Zip code is required.')
        elif not zip_code.isdigit():
            errors.append('Zip code must be numeric.')

        if errors:
            for error in errors:
                messages.error(request, error)
            context = {
                'cart_items': cart_items,
                'subtotal': subtotal,
                'tax': tax,
                'total': total,
                'item_count': item_count,
                'form_values': {
                    'name': name,
                    'email': email,
                    'address': address1,
                    'address2': address2,
                    'city': city,
                    'state': state,
                    'zip': zip_code,
                    'phone': phone,
                }
            }
            return render(request, 'checkout.html', context)

        # Paystack needs amount in Kobo (integer)
        amount_in_kobo = int((total * 100).quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
        items_json = json.dumps(serializable_cart)

        try:
            with transaction.atomic():
                # Map the fields to match your actual model
                order = Orders.objects.create(
                    items_json=items_json,
                    name=name,
                    amount=int(total), # Converting Decimal to Integer for your model
                    email=email,
                    address1=address1,
                    address2=address2,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    phone=phone,
                    paymentstatus='Pending' # You named it paymentstatus, not status
                )
                OrderUpdate.objects.create(
                    Order_id=order.order_id, 
                    update_desc="Order initiated. Awaiting Paystack confirmation."
                )

            # ... Paystack setup follows ...
            # Use order.order_id here

            # Initialize Paystack
            url = "https://api.paystack.co/transaction/initialize"
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json",
            }
            
            callback_url = request.build_absolute_uri(reverse('events:Handlerequest'))
            paystack_data = {
                "email": email,
                "amount": amount_in_kobo,
                "callback_url": callback_url,
                "reference": f"ORD_{order.order_id}_{int(time.time())}",
                "metadata": {
                    "order_id": order.order_id,
                }
            }

            if not getattr(settings, 'PAYSTACK_SECRET_KEY', None):
                messages.error(request, "Payment provider not configured.")
                return redirect('events:checkout')

            try:
                response = requests.post(url, headers=headers, json=paystack_data, timeout=15)
                response.raise_for_status()  # Raise for bad status
                res_data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error('Paystack API request failed: %s', str(e))
                messages.error(request, "Payment service temporarily unavailable. Please try again.")
                return redirect('events:checkout')
            except ValueError as e:
                logger.error('Invalid JSON response from Paystack: %s', str(e))
                messages.error(request, "Payment service error. Please try again.")
                return redirect('events:checkout')

            if res_data.get('status'):
                return redirect(res_data['data']['authorization_url'])
            else:
                error_msg = res_data.get('message', 'Initialization failed.')
                messages.error(request, f'Payment setup failed: {error_msg}')
                return redirect('events:checkout')

        except Exception as e:
            logger.error('Checkout error: %s', str(e), exc_info=True)
            messages.error(request, "An internal error occurred. Please try again.")
            return redirect('events:checkout')

    # 3. Render Page (GET)
    context = {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'item_count': item_count,
        'form_values': {
            'name': '',
            'email': request.user.email if request.user.is_authenticated else '',
            'address': '',
            'address2': '',
            'city': '',
            'state': '',
            'zip': '',
            'phone': '',
        }
    }
    return render(request, 'checkout.html', context)



def handlerequest(request):
    # Paystack sends a GET request with a 'reference' query parameter
    reference = request.GET.get('reference')
    
    if not reference:
        return render(request, 'paymentstatus.html', {'status': 'No reference found'})

    # 1. Verify the transaction with Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }
    
    response = requests.get(url, headers=headers)
    res_data = response.json()

    if res_data.get('status') and res_data['data']['status'] == 'success':
        # 2. Extract our original Order ID from the reference
        # Recall we set reference as f"ORD_{order.order_id}_{timestamp}"
        try:
            # Splits "ORD_45_171455" into ['ORD', '45', '171455'] and takes index 1
            raw_id = reference.split('_')[1]
            
            # 3. Update Order Status in Database
            order = Orders.objects.get(order_id=raw_id)
            order.paymentstatus = "PAID"
            order.amountpaid = res_data['data']['amount'] / 100  # Convert back from Kobo to Naira
            order.save()

            # Record the update
            update = OrderUpdate(Order_id=raw_id, update_desc="Payment Successful - Order is being processed")
            update.save()

            return render(request, 'paymentstatus.html', {
                'status': 'Success', 
                'order_id': raw_id,
                'amount': res_data['data']['amount'] / 100  # Convert back from Kobo to Naira
            })
        except (Orders.DoesNotExist, IndexError):
            return render(request, 'paymentstatus.html', {'status': 'Order not found'})
    else:
        # Payment failed or was cancelled
        return render(request, 'paymentstatus.html', {'status': 'Failed'})


def profile(request):
    if not request.user.is_authenticated:
        messages.warning(request,"Login & Try Again")
        return redirect('account:handlelogin')
    currentuser = request.user.username
    items = Orders.objects.filter(email=currentuser)
    for i in items:
        print(i.oid)
        myid = i.oid
        rid = myid.replace("ShopyCart", "")
        print(rid)
    status = OrderUpdate.objects.filter(Order_id__in=[i.order_id for i in items])


    # context = {"items":items}
    for j in status:
        print(j.update_desc)

    context = {"items": items, "status":status}
    # print(currentuser)
    return render(request, "profile.html", context)


def thanks_page(request):
    return render(request, 'thanks.html')

def submit_feedback(request):
    if request.method == "POST":
        comment = request.POST.get('comment')
        
        # Save to database
        feedback = Feedback.objects.create(
            user=request.user if request.user.is_authenticated else None,
            comment=comment
        )
        feedback.save()
        
        messages.success(request, "Thank you for your feedback!")
        return redirect('events:base') # Take them back home
    return redirect('events:base')



def cart_detail(request):
    cart = request.session.get('cart', {})
    subtotal = Decimal('0.00')
    cart_items = []

    for item_id, item in cart.items():
        price = Decimal(str(item.get('price', 0)))
        quantity = item.get('quantity', 0)
        item_total = price * quantity
        item['total_price'] = item_total
        item['id'] = item_id
        cart_items.append(item)
        subtotal += item_total

    tax_rate = Decimal('0.03')
    tax = (subtotal * tax_rate).quantize(Decimal('0.01'))
    total = subtotal + tax

    context = {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
    }
    return render(request, 'events/cart_detail.html', context)


def remove_from_cart(request, product_id):
    if request.method == 'POST':
        cart = request.session.get('cart', {})
        item_key = str(product_id)

        if item_key in cart:
            del cart[item_key]
            request.session['cart'] = cart
            messages.success(request, 'Item removed from cart.')
        else:
            messages.error(request, 'Item not found in cart.')

    return redirect('events:cart_detail')


def menu_view(request):
    # Meals
    local_dishes = Product.objects.filter(category__icontains='Local', is_available=True)
    snacks = Product.objects.filter(category__icontains='Snacks', is_available=True)
    intercontinental = Product.objects.filter(category__icontains='Intercontinental', is_available=True)
    
    # Drinks
    drink_keywords = [
        'wine', 'champagne', 'rum', 'alcohol', 'beverage', 'drink',
        'cocktail', 'spirits', 'beer', 'juice', 'soda', 'water', 'zobo'
    ]
    drinks_query = Q()
    for keyword in drink_keywords:
        drinks_query |= Q(category__icontains=keyword) | Q(name__icontains=keyword)

    drinks = Product.objects.filter(drinks_query, is_available=True)
    wines = drinks.filter(category__icontains='wine')
    champagne = drinks.filter(category__icontains='champagne')
    rum = drinks.filter(category__icontains='rum')
    alcohol = drinks.filter(category__icontains='alcohol')
    beverages = drinks.filter(category__icontains='beverage')

    context = {
        'local_dishes': local_dishes,
        'snacks': snacks,
        'intercontinental': intercontinental,
        'wines': wines,
        'champagne': champagne,
        'rum': rum,
        'alcohol': alcohol,
        'beverages': beverages,
        'drinks': drinks,
    }
    return render(request, 'events/menu.html', context)


def contact_us(request):
    if request.method == "POST":
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message_content = request.POST.get('message', '')

        # Construct the email content
        full_message = f"Message from: {name} ({email})\n\n{message_content}"

        word_count = len(message_content.split())

        if word_count > 50:
            messages.error(request, "Message is too long! Please keep it under 50 words.")
            return redirect(request.META.get('HTTP_REFERER'))
        
        # Send the email
        send_mail(
            subject,
            full_message,
            email, # From customer email
            ['your-email@gmail.com'], # To your email
        )
        
        messages.success(request, "Your message has been sent. Thank you!")
        return redirect('events:base') # Redirect back to home
    
    return redirect('events:base')

def product_detail(request, pk):
    
    product_item = get_object_or_404(Product, pk=pk)
    
    
    print(f"DEBUG: Found product {product_item.name} with ID {pk}")
    
    return render(request, 'events/item_detail_view.html', {'product': product_item})



def add_to_cart(request, product_id):
    
    product = get_object_or_404(Product, pk=product_id)
    quantity = 1

    if request.method == 'POST':
        try:
            quantity = max(1, int(request.POST.get('quantity', 1)))
        except (ValueError, TypeError):
            quantity = 1

    cart = request.session.get('cart', {})
    item_key = str(product_id)

    if item_key in cart:
        cart[item_key]['quantity'] += quantity
    else:
        cart[item_key] = {
            'name': product.name,
            'price': float(product.price),
            'quantity': quantity,
            'image': product.image.url if getattr(product, 'image', None) else ''
        }

    request.session['cart'] = cart
    messages.success(request, f"{product.name} added to cart.")
    return redirect('events:product_detail', pk=product_id)