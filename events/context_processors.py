def cart_count(request):
    count = 0
    cart = request.session.get('cart', {})
    for item in cart.values():
        count += item.get('quantity', 0)
    return {'cart_count': count}