from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Query, Path
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models.group.student_group import GroupColor
from app.schemas.group.student_group import StudentGroupResponseSchema, StudentGroupCreateSchema, \
    StudentGroupUpdateSchema, StudentGroupCardSchema, GroupCoverImageResponseSchema, GroupMemberTableItemSchema
from app.services.group.student_group_service import get_student_group_service, StudentGroupService

student_group_router = APIRouter(prefix="", )


@student_group_router.post("/", response_model=StudentGroupResponseSchema)
async def create_group(
        name: Annotated[str, Form(..., min_length=2, max_length=120)],
        subject_id: Annotated[int | None, Form()] = None,
        color: Annotated[GroupColor, Form()] = GroupColor.TEAL,
        description: Annotated[str | None, Form(max_length=1000)] = None,
        student_ids: Annotated[str, Form()] = "[]",
        cover_image: UploadFile | None = File(None),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    payload = StudentGroupCreateSchema(
        name=name,
        subject_id=subject_id,
        color=color,
        description=description,
        student_ids=list(map(int, student_ids.split(","))),
    )
    return await service.create_group(current_user.id, payload, cover_image)


@student_group_router.put("/{group_id}", status_code=status.HTTP_201_CREATED)
async def update_group(
        group_id: int,
        payload: StudentGroupUpdateSchema,
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    try:
        return await service.update_group(group_id, current_user.id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@student_group_router.put("/{group_id}/upload/image", response_model=GroupCoverImageResponseSchema)
async def upload_image(
        group_id: int,
        file: UploadFile = File(None),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service)
):
    cover_image = await service.update_group_image(group_id, current_user.id, file)
    return GroupCoverImageResponseSchema(cover_image=cover_image)


# Delete group image

@student_group_router.delete("/{group_id}/remove/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
        group_id: int,
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service)
):
    await service.delete_group_image(group_id, current_user.id)
    return {"detail": "Group image deleted successfully"}


@student_group_router.put("/{group_id}/add/members", status_code=status.HTTP_201_CREATED)
async def add_members(
        group_id: int,
        student_ids: Annotated[str, Form()] = "[]",
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    try:
        await service.add_members(group_id, current_user.id, list(map(int, student_ids.split(","))))
        return {"detail": "Members added successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@student_group_router.delete("/{group_id}/remove/members", status_code=status.HTTP_204_NO_CONTENT)
async def remove_members(
        group_id: int,
        student_ids: Annotated[str, Form()] = "[]",
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    await service.remove_members(group_id, current_user.id, list(map(int, student_ids.split(","))))
    return {"detail": "Members removed successfully"}


# group members
@student_group_router.get("/{group_id}/members", response_model=Page[GroupMemberTableItemSchema])
async def get_members(
        group_id: int = Path(..., description="ID of the student group"),
        search: str | None = Query(None, description="Search  by group name"),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    return await service.group_members(group_id, current_user.id, search)


@student_group_router.get("/", response_model=Page[StudentGroupCardSchema])
async def list_groups(
        search: str | None = Query(None, description="Search  by group name"),
        subject_id: int | None = Query(None, description="Filter by subject ID"),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    return await service.list_groups(current_user.id, search=search, subject_id=subject_id)
