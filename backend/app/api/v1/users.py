from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select

from app.api.deps import DB, Pagination, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.rbac import ALL_PERMISSIONS, SUPER_ADMIN
from app.core.security import hash_password
from app.models.auth import Permission, Role, User
from app.repositories.base import apply_sort, like, page_response, paginate
from app.schemas.auth import (
    PermissionOut,
    RoleCreate,
    RoleDetail,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message, Page
from app.services import audit, auth_service

router = APIRouter(tags=["users"])


def _role_detail(role: Role) -> RoleDetail:
    return RoleDetail(
        id=role.id, name=role.name, description=role.description, is_system=role.is_system,
        permissions=sorted(p.code for p in role.permissions),
    )


@router.get("/users", response_model=Page[UserOut])
def list_users(
    db: DB, p: Pagination, _: Annotated[User, Depends(require("user.read"))],
    role_id: int | None = None, is_active: bool | None = None,
):
    stmt = select(User).where(User.is_deleted.is_(False))
    if p.search:
        stmt = stmt.where(or_(User.full_name.ilike(like(p.search)), User.email.ilike(like(p.search))))
    if role_id:
        stmt = stmt.where(User.roles.any(Role.id == role_id))
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    stmt = apply_sort(stmt, User, p.sort, {"full_name", "email", "created_at", "last_login_at"}, User.full_name)
    rows, total = paginate(db, stmt, p)
    return page_response([UserOut.model_validate(r) for r in rows], total, p)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: DB, actor: Annotated[User, Depends(require("user.create"))]):
    _guard_super_admin_roles(db, actor, body.role_ids)
    user = auth_service.create_user(
        db, email=body.email, full_name=body.full_name, password=body.password, role_ids=body.role_ids,
        phone=body.phone, max_discount_percent=body.max_discount_percent, must_change_password=body.must_change_password,
    )
    audit.record(db, user=actor, action="user.create", entity="user", entity_id=user.id,
                 new={"email": user.email, "roles": user.role_names}, request=request)
    db.commit()
    return user


def _guard_super_admin_roles(db: DB, actor: User, role_ids: list[int]) -> None:
    """Only a super admin may hand out the super-admin role."""
    sa = db.scalar(select(Role).where(Role.name == SUPER_ADMIN))
    if sa and sa.id in role_ids and SUPER_ADMIN not in actor.role_names:
        raise ValidationFailed("Only a Super Admin can assign the Super Admin role")


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DB, _: Annotated[User, Depends(require("user.read"))]):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: DB, actor: Annotated[User, Depends(require("user.update"))]):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found")
    if SUPER_ADMIN in user.role_names and SUPER_ADMIN not in actor.role_names:
        raise ValidationFailed("Only a Super Admin can modify a Super Admin")
    data = body.model_dump(exclude_unset=True)
    old = {"full_name": user.full_name, "is_active": user.is_active, "roles": user.role_names}
    if "role_ids" in data and data["role_ids"] is not None:
        _guard_super_admin_roles(db, actor, data["role_ids"])
        roles = list(db.scalars(select(Role).where(Role.id.in_(data["role_ids"]))))
        if len(roles) != len(set(data["role_ids"])) or not roles:
            raise ValidationFailed("One or more roles do not exist")
        user.roles = roles
    if data.get("is_active") is False and user.id == actor.id:
        raise ValidationFailed("You cannot deactivate your own account")
    for field in ("full_name", "phone", "is_active", "max_discount_percent"):
        if field in data:
            setattr(user, field, data[field])
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
        user.must_change_password = True
        auth_service.revoke_all_sessions(db, user.id)
    if data.get("is_active") is False:
        auth_service.revoke_all_sessions(db, user.id)
    audit.record(db, user=actor, action="user.update", entity="user", entity_id=user.id, old=old,
                 new={"full_name": user.full_name, "is_active": user.is_active, "roles": user.role_names,
                      "password_reset": bool(data.get("password"))}, request=request)
    db.commit()
    return user


@router.delete("/users/{user_id}", response_model=Message)
def delete_user(user_id: int, request: Request, db: DB, actor: Annotated[User, Depends(require("user.delete"))]):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found")
    if user.id == actor.id:
        raise ValidationFailed("You cannot delete your own account")
    if SUPER_ADMIN in user.role_names and SUPER_ADMIN not in actor.role_names:
        raise ValidationFailed("Only a Super Admin can delete a Super Admin")
    user.is_deleted, user.is_active = True, False
    auth_service.revoke_all_sessions(db, user.id)
    audit.record(db, user=actor, action="user.delete", entity="user", entity_id=user.id, request=request)
    db.commit()
    return Message(message="User deactivated")


# ---- roles & permissions -------------------------------------------------------------

@router.get("/roles", response_model=list[RoleDetail])
def list_roles(db: DB, _: Annotated[User, Depends(require("user.read", "role.manage", any_of=True))]):
    return [_role_detail(r) for r in db.scalars(select(Role).order_by(Role.id))]


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: DB, _: Annotated[User, Depends(require("user.read", "role.manage", any_of=True))]):
    return list(db.scalars(select(Permission).order_by(Permission.module, Permission.code)))


@router.post("/roles", response_model=RoleDetail, status_code=201)
def create_role(body: RoleCreate, request: Request, db: DB, actor: Annotated[User, Depends(require("role.manage"))]):
    name = body.name.strip().upper().replace(" ", "_")
    if db.scalar(select(Role.id).where(Role.name == name)):
        raise ConflictError("A role with this name already exists")
    unknown = set(body.permissions) - set(ALL_PERMISSIONS)
    if unknown:
        raise ValidationFailed(f"Unknown permissions: {', '.join(sorted(unknown))}")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    role = Role(name=name, description=body.description, is_system=False)
    role.permissions = perms
    db.add(role)
    db.flush()
    audit.record(db, user=actor, action="role.create", entity="role", entity_id=role.id,
                 new={"name": name, "permissions": sorted(body.permissions)}, request=request)
    db.commit()
    return _role_detail(role)


@router.patch("/roles/{role_id}", response_model=RoleDetail)
def update_role(role_id: int, body: RoleUpdate, request: Request, db: DB, actor: Annotated[User, Depends(require("role.manage"))]):
    role = db.get(Role, role_id)
    if not role:
        raise NotFoundError("Role not found")
    if role.name == SUPER_ADMIN:
        raise ValidationFailed("The Super Admin role cannot be modified")
    old = sorted(p.code for p in role.permissions)
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        unknown = set(body.permissions) - set(ALL_PERMISSIONS)
        if unknown:
            raise ValidationFailed(f"Unknown permissions: {', '.join(sorted(unknown))}")
        role.permissions = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    audit.record(db, user=actor, action="role.update", entity="role", entity_id=role.id,
                 old={"permissions": old}, new={"permissions": sorted(p.code for p in role.permissions)}, request=request)
    db.commit()
    return _role_detail(role)


@router.delete("/roles/{role_id}", response_model=Message)
def delete_role(role_id: int, request: Request, db: DB, actor: Annotated[User, Depends(require("role.manage"))]):
    role = db.get(Role, role_id)
    if not role:
        raise NotFoundError("Role not found")
    if role.is_system:
        raise ValidationFailed("System roles cannot be deleted")
    if db.scalar(select(User.id).where(User.roles.any(Role.id == role_id)).limit(1)):
        raise ConflictError("Role is assigned to users; reassign them first")
    db.delete(role)
    audit.record(db, user=actor, action="role.delete", entity="role", entity_id=role_id, request=request)
    db.commit()
    return Message(message="Role deleted")
