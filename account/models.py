from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone
import random

# Create your models here.

class ActivationPin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='activation_pin')
    pin = models.CharField(max_length=6, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"PIN for {self.user.email}"

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    @staticmethod
    def generate_pin():
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])

    @classmethod
    def create_for_user(cls, user):
        """Create or update PIN for user with 15-minute expiry"""
        pin = cls.generate_pin()
        expires_at = timezone.now() + timedelta(minutes=15)
        
        # Delete old PIN if exists
        cls.objects.filter(user=user).delete()
        
        return cls.objects.create(user=user, pin=pin, expires_at=expires_at)
