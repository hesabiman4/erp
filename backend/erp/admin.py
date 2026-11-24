"""Restricted maintenance surface for account recovery, not transaction editing."""
from django.contrib import admin
from .models import Business, Membership, LegalEntity

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display=('user','business','role','active','all_locations')
    list_filter=('business','active')
    search_fields=('user__username','business__name')

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display=('name','slug','manufacturing_mode','closed_through')
    readonly_fields=('closed_through',)

admin.site.register(LegalEntity)
