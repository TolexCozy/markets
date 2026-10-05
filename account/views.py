from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import DjangoUnicodeDecodeError, force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import View
from django_ratelimit.decorators import ratelimit

from events.models import OrderUpdate, Orders
from .models import ActivationPin
from .utils import generate_token


@ratelimit(key='ip', rate='5/m', block=True)
def signup(request):
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        password = request.POST.get('pass1', '')
        confirm_password = request.POST.get('pass2', '')

        if password != confirm_password:
            messages.warning(request, "Passwords do not match")
            return redirect('account:signup')

        user, created = User.objects.get_or_create(
            username=email,
            defaults={'email': email, 'is_active': False}
        )

        if not created:
            if user.is_active:
                messages.error(request, "Email is already registered and active. Please login.")
                return redirect('account:handlelogin')
            else:
                user.set_password(password)
                user.save()
        else:
            user.set_password(password)
            user.save()

        activation_pin = ActivationPin.create_for_user(user)
        current_site = get_current_site(request)

        message = render_to_string('activate.html', {
            'user': user,
            'domain': current_site.domain,
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': generate_token.make_token(user),
            'pin': activation_pin.pin
        })

        email_message = EmailMessage(
            subject="Activate Your Account",
            body=message,
            from_email=settings.EMAIL_HOST_USER,
            to=[email]
        )
        email_message.content_subtype = 'html'

        try:
            sent = email_message.send()
            if sent == 1:
                messages.success(request, "Account created! Check your email for your 6-digit PIN.")
            else:
                messages.error(request, "Email failed. Try again.")
        except Exception as e:
            messages.error(request, "Email server error. Try again later.")

        verify_url = reverse('account:verify_pin')
        query_string = urlencode({'email': email})
        return redirect(f"{verify_url}?{query_string}")

    return render(request, "account/signup.html")


@login_required
def profile(request):
    currentuser = request.user.username
    items = Orders.objects.filter(email=currentuser)
    order_data = []

    for i in items:
        myid = i.oid
        try:
            rid = int(myid.replace("ShopyCart", ""))
            status = OrderUpdate.objects.filter(Order_id=rid).order_by('-timestamp').first()
        except ValueError:
            status = None

        order_data.append({
            'order': i,
            'status': status
        })

    context = {"order_data": order_data}
    return render(request, "profile.html", context)


class ActivateAccountView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, DjangoUnicodeDecodeError):
            user = None

        if user is not None and generate_token.check_token(user, token):
            if user.is_active:
                messages.info(request, "Account already activated.")
                return redirect('account:handlelogin')

            user.is_active = True
            user.save()

            messages.success(request, "Account activated successfully.")
            return redirect('account:handlelogin')

        messages.error(request, "Activation link is invalid or expired.")
        return redirect('account:handlelogin')


def handlelogin(request):
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == "POST":
        username = request.POST.get('email', '').strip()
        password = request.POST.get('pass1', '')

        user_obj = User.objects.filter(username=username).first()

        if user_obj and not user_obj.is_active:
            if user_obj.check_password(password):
                messages.error(request, "Account not activated. Please check your email for the activation link or PIN.")
                return redirect('account:handlelogin')

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful!")

            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('/')
        else:
            messages.error(request, "Invalid username or password.")
            return redirect('account:handlelogin')

    return render(request, 'account/login.html')


def handlelogout(request):
    logout(request)
    messages.info(request, "Logout successful.")
    return redirect('account:handlelogin')


class RequestResetEmailView(View):
    def get(self, request):
        return render(request, 'account/request-reset-email.html')

    def post(self, request):
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email=email).first()

        if user:
            email_subject = "Reset Your Password"
            message = render_to_string('account/request-user-password.html', {
                'domain': get_current_site(request).domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': PasswordResetTokenGenerator().make_token(user)
            })
            email_message = EmailMessage(email_subject, message, settings.EMAIL_HOST_USER, [email])
            email_message.content_subtype = 'html'
            email_message.send()
            messages.success(request, "Instructions to reset your password have been sent to your email.")
        else:
            messages.error(request, "No user is associated with this email address.")

        return render(request, 'account/request-reset-email.html')


class SetNewPasswordView(View):
    def get(self, request, uidb64, token):
        context = {'uidb64': uidb64, 'token': token}

        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)

            if not PasswordResetTokenGenerator().check_token(user, token):
                messages.warning(request, "Password reset link is invalid.")
                return redirect('account:request-reset-email')

        except (DjangoUnicodeDecodeError, User.DoesNotExist):
            messages.error(request, "Something went wrong.")
            return redirect('account:request-reset-email')

        return render(request, 'account/set-new-password.html', context)

    def post(self, request, uidb64, token):
        password = request.POST.get('pass1', '')
        confirm_password = request.POST.get('pass2', '')
        context = {'uidb64': uidb64, 'token': token}

        if password != confirm_password:
            messages.warning(request, "Passwords do not match.")
            return render(request, 'account/set-new-password.html', context)

        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)

            if not PasswordResetTokenGenerator().check_token(user, token):
                messages.warning(request, "Token is invalid or expired.")
                return redirect('account:request-reset-email')

            user.set_password(password)
            user.save()
            messages.success(request, "Password reset successful! You can now log in.")
            return redirect('account:handlelogin')

        except (DjangoUnicodeDecodeError, User.DoesNotExist):
            messages.error(request, "Something went wrong.")
            return render(request, 'account/set-new-password.html', context)


@ratelimit(key='ip', rate='3/m', block=True)
def resend_activation(request):
    email = request.GET.get('email', '') or request.POST.get('email', '')

    if request.method == "POST":
        email = request.POST.get('email', '').strip()

        if not email:
            messages.error(request, "Please enter your email address.")
            return render(request, "account/resend-activation.html", {'email': email})

        try:
            user = User.objects.get(email=email)

            if user.is_active:
                messages.info(request, "Account is already activated. Please log in.")
                return redirect('account:handlelogin')

            activation_pin = ActivationPin.create_for_user(user)
            current_site = get_current_site(request)

            message = render_to_string('activate.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': generate_token.make_token(user),
                'pin': activation_pin.pin
            })

            email_message = EmailMessage(
                subject="Your New Activation PIN",
                body=message,
                from_email=settings.EMAIL_HOST_USER,
                to=[email]
            )
            email_message.content_subtype = 'html'

            try:
                sent = email_message.send()
                if sent == 1:
                    messages.success(request, f"New 6-digit PIN sent to {email}!")
                    verify_url = reverse('account:verify_pin')
                    query_string = urlencode({'email': email})
                    return redirect(f"{verify_url}?{query_string}")
                else:
                    messages.error(request, "Email failed to send. Try again.")
            except Exception as e:
                messages.error(request, f"Email server error: {e}")

            return render(request, "account/resend-activation.html", {'email': email})

        except User.DoesNotExist:
            messages.error(request, "No account found with this email.")
            return render(request, "account/resend-activation.html", {'email': email})

    return render(request, "account/resend-activation.html", {'email': email})


@ratelimit(key='ip', rate='5/m', block=True)
def verify_pin(request):
    email = request.GET.get('email', '') or request.POST.get('email', '')

    if request.method == "POST":
        pin = request.POST.get('pin', '').strip()

        if not email or not pin:
            messages.error(request, "Please provide both email and 6-digit PIN.")
            return render(request, "account/verify-pin.html", {'email': email})

        try:
            user = User.objects.get(email=email)

            activation_pin = ActivationPin.objects.filter(
                user=user, 
                is_used=False
            ).order_by('-created_at').first()

            if not activation_pin:
                messages.error(request, "No pending PIN found for this account. Request a new one.")
                return render(request, "account/verify-pin.html", {'email': email})

            if not activation_pin.is_valid():
                messages.error(request, "PIN has expired. Request a new one.")
                return render(request, "account/verify-pin.html", {'email': email})

            if activation_pin.pin == pin:
                user.is_active = True
                user.save()

                activation_pin.is_used = True
                activation_pin.save()

                messages.success(request, "Account activated successfully! Please log in.")
                return redirect('account:handlelogin')
            else:
                messages.error(request, "Invalid PIN. Try again.")
                return render(request, "account/verify-pin.html", {'email': email})

        except User.DoesNotExist:
            messages.error(request, "Email not found or no pending activation.")
            return render(request, "account/verify-pin.html", {'email': email})

    return render(request, "account/verify-pin.html", {'email': email})