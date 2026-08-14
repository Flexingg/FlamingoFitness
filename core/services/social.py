"""Social service: friends & Flocks (Phase 8, docs/13 §5.3).

Friends:
  * ``send_friend_request(from_user, username)`` - pending request; a reverse
    pending request auto-accepts (both sides asked).
  * ``respond_friend_request`` / ``remove_friend`` / ``friends_of``.
  * ``search_users`` - "find friends" with relationship annotations.

Flocks (up to FLOCK_MAX_MEMBERS):
  * ``create_flock`` / ``invite_to_flock`` / ``respond_flock_invite`` /
    ``leave_flock`` / ``flock_weekly_standings``.

All mutators return ``(ok, value)`` where ``value`` is an error dict
``{"message": str, "status": int}`` on failure, or the useful object on
success - views map that straight onto ``_json_error`` / ``JsonResponse``.
"""

import logging

from django.contrib.auth import get_user_model
from django.db.models import Q

from ..models import Flock, FlockInvite, FlockMembership, Friendship
from .leagues import weekly_xp_map

logger = logging.getLogger(__name__)

# Duolingo-family sized groups (docs/12 §3).
FLOCK_MAX_MEMBERS = 8


def _err(message, status=400):
    return {"message": message, "status": status}


def _pair_query(a, b):
    """Friendship rows in EITHER direction between two users."""
    return Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a)


def get_friendship(a, b):
    return Friendship.objects.filter(_pair_query(a, b)).first()


def friends_of(user):
    """The users this person is friends with (accepted, either direction)."""
    rows = Friendship.objects.filter(
        Q(from_user=user) | Q(to_user=user),
        status=Friendship.Status.ACCEPTED,
    )
    ids = [r.to_user_id if r.from_user_id == user.pk else r.from_user_id for r in rows]
    return list(get_user_model().objects.filter(pk__in=ids))


def send_friend_request(from_user, username):
    """Create (or auto-accept) a friend request by username."""
    UserModel = get_user_model()
    username = (username or "").strip()
    if not username:
        return False, _err("Username is required.")
    target = UserModel.objects.filter(username__iexact=username).first()
    if target is None:
        return False, _err("No player with that username.", 404)
    if target.pk == from_user.pk:
        return False, _err("You cannot friend yourself.")

    existing = get_friendship(from_user, target)
    if existing is not None:
        if existing.status == Friendship.Status.ACCEPTED:
            return False, _err("You are already friends.")
        if existing.from_user_id == from_user.pk:
            return False, _err("Friend request already sent.")
        # Reverse pending request -> both sides asked: instant friends.
        existing.status = Friendship.Status.ACCEPTED
        existing.save(update_fields=["status", "updated_at"])
        return True, existing

    friendship = Friendship.objects.create(
        from_user=from_user, to_user=target, status=Friendship.Status.PENDING
    )
    return True, friendship


def respond_friend_request(user, from_user_id, accept):
    """Recipient accepts / declines a pending request addressed to them."""
    friendship = Friendship.objects.filter(
        from_user_id=from_user_id, to_user=user, status=Friendship.Status.PENDING
    ).first()
    if friendship is None:
        return False, _err("No pending request from that player.", 404)
    if accept:
        friendship.status = Friendship.Status.ACCEPTED
        friendship.save(update_fields=["status", "updated_at"])
    else:
        friendship.delete()
    return True, friendship


def remove_friend(user, friend_id):
    friendship = Friendship.objects.filter(
        Q(from_user_id=user.pk, to_user_id=friend_id)
        | Q(from_user_id=friend_id, to_user_id=user.pk),
        status=Friendship.Status.ACCEPTED,
    ).first()
    if friendship is None:
        return False, _err("You are not friends with that player.", 404)
    friendship.delete()
    return True, None


def search_users(query, viewer, limit=10):
    """Find-players search: username icontains, relationship annotated."""
    query = (query or "").strip()
    if not query:
        return []
    UserModel = get_user_model()
    candidates = UserModel.objects.filter(
        username__icontains=query, is_active=True
    ).exclude(pk=viewer.pk).order_by("username")[:limit]

    results = []
    for candidate in candidates:
        friendship = get_friendship(viewer, candidate)
        if friendship is None:
            relationship = "none"
        elif friendship.status == Friendship.Status.ACCEPTED:
            relationship = "friends"
        elif friendship.from_user_id == viewer.pk:
            relationship = "pending_out"
        else:
            relationship = "pending_in"
        results.append(
            {
                "id": candidate.pk,
                "username": candidate.username,
                "avatar": candidate.avatar,
                "relationship": relationship,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Flocks
# ---------------------------------------------------------------------------
def membership_of(user):
    return FlockMembership.objects.filter(user=user).select_related("flock").first()


def create_flock(user, name):
    name = (name or "").strip()
    if not name:
        return False, _err("Flock name is required.")
    if len(name) > 80:
        return False, _err("Flock name must be 80 characters or fewer.")
    if membership_of(user) is not None:
        return False, _err("You are already in a flock.")
    flock = Flock.objects.create(name=name, created_by=user)
    FlockMembership.objects.create(
        flock=flock, user=user, role=FlockMembership.Role.OWNER
    )
    return True, flock


def invite_to_flock(inviter, user_id):
    membership = membership_of(inviter)
    if membership is None:
        return False, _err("You are not in a flock.")
    if membership.role != FlockMembership.Role.OWNER:
        return False, _err("Only the flock owner can invite players.")
    target = get_user_model().objects.filter(pk=user_id).first()
    if target is None:
        return False, _err("Player not found.", 404)
    friend_ids = {friend.pk for friend in friends_of(inviter)}
    if target.pk not in friend_ids:
        return False, _err("You can only invite friends.")
    if membership_of(target) is not None:
        return False, _err("That player is already in a flock.")
    invite, _ = FlockInvite.objects.update_or_create(
        flock=membership.flock,
        user=target,
        defaults={"status": FlockInvite.Status.PENDING, "invited_by": inviter},
    )
    return True, invite


def respond_flock_invite(user, flock_id, accept):
    invite = FlockInvite.objects.filter(
        flock_id=flock_id, user=user, status=FlockInvite.Status.PENDING
    ).first()
    if invite is None:
        return False, _err("No pending invite for that flock.", 404)
    if not accept:
        invite.status = FlockInvite.Status.DECLINED
        invite.save(update_fields=["status", "updated_at"])
        return True, invite
    if membership_of(user) is not None:
        return False, _err("You are already in a flock.")
    if invite.flock.memberships.count() >= FLOCK_MAX_MEMBERS:
        return False, _err("That flock is full.")
    FlockMembership.objects.create(flock=invite.flock, user=user)
    invite.status = FlockInvite.Status.ACCEPTED
    invite.save(update_fields=["status", "updated_at"])
    return True, invite


def leave_flock(user):
    membership = membership_of(user)
    if membership is None:
        return False, _err("You are not in a flock.")
    flock = membership.flock
    membership.delete()
    if flock.memberships.count() == 0:
        flock.delete()  # last one out turns off the lights (cascades invites)
    return True, None


def flock_weekly_standings(flock, now=None):
    """Members ranked by Effort XP this league week (docs/12 §3 shared board)."""
    xp_map = weekly_xp_map(now=now)
    members = []
    for membership in flock.memberships.select_related("user"):
        members.append(
            {
                "id": membership.user.pk,
                "username": membership.user.username,
                "avatar": membership.user.avatar,
                "role": membership.role,
                "weekly_xp": xp_map.get(membership.user.pk, 0),
            }
        )
    members.sort(key=lambda m: (-m["weekly_xp"], m["username"]))
    return members


def _serialize_flock(membership, viewer, now=None):
    flock = membership.flock
    members = flock_weekly_standings(flock, now=now)
    for member in members:
        member["is_you"] = member["id"] == viewer.pk
    return {
        "id": flock.pk,
        "name": flock.name,
        "icon": flock.icon,
        "member_count": len(members),
        "max_members": FLOCK_MAX_MEMBERS,
        "my_role": membership.role,
        "weekly_total_xp": sum(m["weekly_xp"] for m in members),
        "members": members,
    }


def social_state(user, q=None, now=None):
    """Payload for ``GET /api/v1/social/`` (docs/13 §6.3)."""
    xp_map = weekly_xp_map(now=now)

    friends = []
    my_membership = membership_of(user)
    my_flock_id = my_membership.flock_id if my_membership else None
    for friend in friends_of(user):
        friend_membership = membership_of(friend)
        friends.append(
            {
                "id": friend.pk,
                "username": friend.username,
                "avatar": friend.avatar,
                "weekly_xp": xp_map.get(friend.pk, 0),
                "same_flock": bool(
                    my_flock_id
                    and friend_membership
                    and friend_membership.flock_id == my_flock_id
                ),
                "in_flock": friend_membership is not None,
            }
        )
    friends.sort(key=lambda f: (-f["weekly_xp"], f["username"]))

    incoming = [
        {
            "id": f.from_user_id,
            "username": f.from_user.username,
            "avatar": f.from_user.avatar,
        }
        for f in Friendship.objects.filter(
            to_user=user, status=Friendship.Status.PENDING
        ).select_related("from_user")
    ]
    outgoing = [
        {
            "id": f.to_user_id,
            "username": f.to_user.username,
            "avatar": f.to_user.avatar,
        }
        for f in Friendship.objects.filter(
            from_user=user, status=Friendship.Status.PENDING
        ).select_related("to_user")
    ]

    flock = _serialize_flock(my_membership, user, now=now) if my_membership else None

    flock_invites = []
    for invite in FlockInvite.objects.filter(
        user=user, status=FlockInvite.Status.PENDING
    ).select_related("flock", "invited_by"):
        flock_invites.append(
            {
                "flock_id": invite.flock_id,
                "name": invite.flock.name,
                "icon": invite.flock.icon,
                "member_count": invite.flock.memberships.count(),
                "invited_by": invite.invited_by.username if invite.invited_by else "",
            }
        )

    return {
        "friends": friends,
        "incoming_requests": incoming,
        "outgoing_requests": outgoing,
        "flock": flock,
        "flock_invites": flock_invites,
        "search_results": search_users(q, user) if q else [],
    }
