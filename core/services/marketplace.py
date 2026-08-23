"""Marketplace Service for Flamingo Fitness (Roadmap item #5).

Handles player-to-player gear trading with Token/Scrap currency, escrow,
and 5% marketplace trading fee.
"""

from django.db import transaction
from django.utils import timezone

from ..models import GearItemDef, MarketplaceListing, PlayerProfile, UserGear
from .combat import profile as combat_profile

MARKETPLACE_FEE_PERCENT = 0.05  # 5% transaction burn


def get_marketplace_state(user, category=None, rarity=None, sort=None):
    """Retrieve active listings, user inventory available to list, and user listings."""
    profile = combat_profile(user)

    # Active listings
    qs = MarketplaceListing.objects.filter(is_active=True).select_related(
        "seller", "gear_item", "gear_item__pack"
    )

    if category:
        qs = qs.filter(gear_item__slot=category)
    if rarity:
        qs = qs.filter(rarity=rarity)

    if sort == "price_asc":
        qs = qs.order_by("price_amount")
    elif sort == "price_desc":
        qs = qs.order_by("-price_amount")
    else:
        qs = qs.order_by("-created_at")

    listings = []
    for l in qs:
        listings.append({
            "id": l.id,
            "seller": l.seller.username,
            "is_mine": l.seller_id == user.id,
            "gear": {
                "id": l.gear_item.id,
                "slug": l.gear_item.slug,
                "name": l.gear_item.name,
                "slot": l.gear_item.slot,
                "icon": l.gear_item.icon,
                "rarity": l.rarity,
                "description": l.gear_item.description,
                "pack_name": l.gear_item.pack.name if l.gear_item.pack else None,
            },
            "price_type": l.price_type,
            "price_amount": l.price_amount,
            "created_at": l.created_at.isoformat(),
        })

    # User's unequipped gear that can be listed
    listable_gear = []
    for ug in UserGear.objects.filter(
        user=user, equipped_slot__isnull=True
    ).select_related("gear_def", "gear_def__pack"):
        # Make sure not already actively listed
        if not MarketplaceListing.objects.filter(user_gear=ug, is_active=True).exists():
            listable_gear.append({
                "user_gear_id": ug.id,
                "slug": ug.gear_def.slug,
                "name": ug.gear_def.name,
                "slot": ug.gear_def.slot,
                "icon": ug.gear_def.icon,
                "rarity": ug.rarity,
                "description": ug.gear_def.description,
            })

    # User's active listings
    my_listings = [l for l in listings if l["is_mine"]]

    # User's past sales/purchases
    recent_activity = []
    for past in (
        MarketplaceListing.objects.filter(is_active=False)
        .filter(seller=user)
        .select_related("buyer", "gear_item")
        .order_by("-sold_at")[:10]
    ):
        if past.sold_at and past.buyer:
            recent_activity.append({
                "id": past.id,
                "type": "sale",
                "gear_name": past.gear_item.name,
                "rarity": past.rarity,
                "other_user": past.buyer.username,
                "price_amount": past.price_amount,
                "price_type": past.price_type,
                "date": past.sold_at.isoformat(),
            })

    for past_buy in (
        MarketplaceListing.objects.filter(is_active=False, buyer=user)
        .select_related("seller", "gear_item")
        .order_by("-sold_at")[:10]
    ):
        if past_buy.sold_at:
            recent_activity.append({
                "id": past_buy.id,
                "type": "purchase",
                "gear_name": past_buy.gear_item.name,
                "rarity": past_buy.rarity,
                "other_user": past_buy.seller.username,
                "price_amount": past_buy.price_amount,
                "price_type": past_buy.price_type,
                "date": past_buy.sold_at.isoformat(),
            })

    recent_activity.sort(key=lambda x: x["date"], reverse=True)

    return {
        "listings": listings,
        "my_listings": my_listings,
        "listable_gear": listable_gear,
        "recent_activity": recent_activity[:15],
        "wallet": {
            "tokens": profile.tokens,
            "scraps": profile.scraps,
        },
    }


@transaction.atomic
def list_gear_item(user, user_gear_id, price_type, price_amount):
    """List an unequipped UserGear item on the marketplace."""
    if price_type not in ("tokens", "scraps"):
        return None, "Price type must be 'tokens' or 'scraps'"
    try:
        price_amount = int(price_amount)
        if price_amount <= 0:
            return None, "Price must be greater than 0"
    except (ValueError, TypeError):
        return None, "Invalid price amount"

    ug = UserGear.objects.filter(pk=user_gear_id, user=user).select_related("gear_def").first()
    if not ug:
        return None, "Gear item not found in your inventory"

    if ug.equipped_slot:
        return None, "Cannot list equipped gear. Please unequip first."

    if MarketplaceListing.objects.filter(user_gear=ug, is_active=True).exists():
        return None, "Item is already listed on the marketplace"

    listing = MarketplaceListing.objects.create(
        seller=user,
        gear_item=ug.gear_def,
        user_gear=ug,
        rarity=ug.rarity,
        price_type=price_type,
        price_amount=price_amount,
        is_active=True,
    )

    return listing, None


@transaction.atomic
def buy_marketplace_item(buyer, listing_id):
    """Purchase an active marketplace listing."""
    listing = (
        MarketplaceListing.objects.select_for_update()
        .filter(pk=listing_id, is_active=True)
        .select_related("seller", "gear_item", "user_gear")
        .first()
    )
    if not listing:
        return None, "Listing is no longer available"

    if listing.seller_id == buyer.id:
        return None, "You cannot purchase your own listing"

    buyer_profile = combat_profile(buyer)
    seller_profile = combat_profile(listing.seller)

    price = listing.price_amount
    price_type = listing.price_type

    if price_type == "tokens":
        if buyer_profile.tokens < price:
            return None, f"Insufficient tokens (need {price}, have {buyer_profile.tokens})"
        buyer_profile.tokens -= price
        fee = int(price * MARKETPLACE_FEE_PERCENT)
        seller_earnings = max(1, price - fee) if price >= 10 else price
        seller_profile.tokens += seller_earnings
    else:  # scraps
        if buyer_profile.scraps < price:
            return None, f"Insufficient scraps (need {price}, have {buyer_profile.scraps})"
        buyer_profile.scraps -= price
        fee = int(price * MARKETPLACE_FEE_PERCENT)
        seller_earnings = max(1, price - fee) if price >= 10 else price
        seller_profile.scraps += seller_earnings

    buyer_profile.save()
    seller_profile.save()

    # Transfer UserGear to buyer
    if listing.user_gear:
        ug = listing.user_gear
        ug.user = buyer
        ug.equipped_slot = None
        ug.save()
    else:
        UserGear.objects.create(
            user=buyer,
            gear_def=listing.gear_item,
            rarity=listing.rarity,
            equipped_slot=None,
        )

    listing.is_active = False
    listing.buyer = buyer
    listing.sold_at = timezone.now()
    listing.save()

    return {
        "success": True,
        "listing_id": listing.id,
        "gear_name": listing.gear_item.name,
        "rarity": listing.rarity,
        "price_amount": price,
        "price_type": price_type,
        "buyer_tokens": buyer_profile.tokens,
        "buyer_scraps": buyer_profile.scraps,
    }, None


@transaction.atomic
def cancel_marketplace_listing(seller, listing_id):
    """Cancel an active marketplace listing."""
    listing = (
        MarketplaceListing.objects.select_for_update()
        .filter(pk=listing_id, seller=seller, is_active=True)
        .first()
    )
    if not listing:
        return None, "Listing not found or already closed"

    listing.is_active = False
    listing.save()
    return listing, None
