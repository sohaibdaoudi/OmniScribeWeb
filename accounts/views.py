from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import SignUpForm


def register(request):
    if request.user.is_authenticated:
        return redirect("lectures:dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("lectures:dashboard")
    else:
        form = SignUpForm()
    return render(request, "accounts/register.html", {"form": form})
