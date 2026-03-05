import json
import os
import uuid
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from limes_outpost.api.dependencies import DBPool, CurrentUser, AnyMember, OperatorOnly
from limes_outpost.api.schemas import (
    VentureCreateRequest, VenturePatchRequest, VentureResponse,
    MemberInviteRequest,
)
from limes_outpost.utils.llm_client import LLMClient

router = APIRouter()
llm = LLMClient()

# Minimal pipeline config for a new venture override.
_DEFAULT_PIPELINE_CONFIG = {
    "workflows": {
        "short_form_video": {"enabled": True},
        "blog_post":        {"enabled": True},
        "social_post":      {"enabled": True},
    }
}

# Default ElevenLabs voice ID (Rachel)
_DEFAULT_TTS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

class StrategyChatRequest(BaseModel):
    message: str

# -----------------------------------------------------------------
#  List ventures for current user
# -----------------------------------------------------------------

@router.get("", response_model=list[VentureResponse])
async def list_ventures(user: CurrentUser, db_pool: DBPool):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT v.id, v.name, v.brand_profile, v.personal_profile, 
                       v.status, v.workflow_schedule, v.timezone, v.tts_voice_id, vm.role
                FROM public.ventures v
                JOIN public.venture_members vm ON v.id = vm.venture_id
                WHERE vm.user_id = %s
            """, (user["id"],))
            rows = cur.fetchall()
            return [
                VentureResponse(
                    id=row[0], 
                    name=row[1], 
                    brand_profile=row[2] or {},
                    personal_profile=row[3] or {}, 
                    status=row[4],
                    workflow_schedule=row[5] or {}, 
                    timezone=row[6],
                    tts_voice_id=row[7], 
                    role=row[8]
                ) for row in rows
            ]
    finally:
        db_pool.putconn(conn)


# -----------------------------------------------------------------
#  Create a new venture
# -----------------------------------------------------------------

@router.post("", response_model=VentureResponse, status_code=status.HTTP_201_CREATED)
async def create_venture(
    body: VentureCreateRequest, 
    user: CurrentUser, 
    db_pool: DBPool
):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            # 1. Insert Venture
            cur.execute("""
                INSERT INTO public.ventures (
                    id, name, brand_profile, personal_profile, 
                    workflow_schedule, timezone, tts_voice_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, brand_profile, personal_profile, status, workflow_schedule, timezone, tts_voice_id
            """, (
                body.id, 
                body.name, 
                json.dumps(body.brand_profile),
                json.dumps(body.personal_profile or {}),
                json.dumps(body.workflow_schedule or {}),
                body.timezone or "UTC",
                body.tts_voice_id or _DEFAULT_TTS_VOICE_ID
            ))
            row = cur.fetchone()
            
            # 2. Add creator as operator
            cur.execute(
                "INSERT INTO public.venture_members (user_id, venture_id, role) VALUES (%s, %s, 'operator')",
                (user["id"], body.id)
            )
            conn.commit()

            # 3. Sync to disk for agents
            _write_brand_profile_to_disk(body.id, body.brand_profile)
            _write_pipeline_config_to_disk(body.id, body.workflow_schedule or {})

            return VentureResponse(
                id=row[0],
                name=row[1],
                brand_profile=row[2],
                personal_profile=row[3],
                status=row[4],
                workflow_schedule=row[5],
                timezone=row[6],
                tts_voice_id=row[7],
                role="operator"
            )
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_pool.putconn(conn)


# -----------------------------------------------------------------
#  Venture Strategy Chat
# -----------------------------------------------------------------

@router.post("/{venture_id}/strategy/chat")
async def venture_strategy_chat(
    venture_id: str,
    request: StrategyChatRequest,
    user: CurrentUser,
    db_pool: DBPool):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, brand_profile, personal_profile 
                FROM public.ventures 
                WHERE id = %s
                """, 
                (venture_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Venture not found")
            
            v_name, v_brand_profile, v_personal_profile = row

        persona_context = json.dumps(v_personal_profile) if v_personal_profile else "No specific persona defined."

        system_prompt = f"""
        You are the 'Lead Strategist' for {v_name}. 
        
        BRAND IDENTITY:
        {json.dumps(v_brand_profile)}
        
        OWNER PERSONA & STYLE:
        {persona_context}
        
        GOAL:
        Provide tactical advice as the founder's right hand. 
        Adopt the communication style defined in the Owner Persona.
        """

        ai_response = llm.generate(
            system_prompt=system_prompt,
            user_prompt=request.message,
            json_mode=False 
        )

        return {"content": ai_response}

    finally:
        db_pool.putconn(conn)


# -----------------------------------------------------------------
#  Get venture detail
# -----------------------------------------------------------------

@router.get("/{venture_id}", response_model=VentureResponse)
async def get_venture(venture_id: str, user: CurrentUser, db_pool: DBPool):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    v.id, 
                    v.name, 
                    v.brand_profile, 
                    v.personal_profile, 
                    v.status, 
                    v.workflow_schedule, 
                    v.timezone, 
                    v.tts_voice_id,
                    vm.role
                FROM public.ventures v
                JOIN public.venture_members vm ON v.id = vm.venture_id
                WHERE v.id = %s AND vm.user_id = %s
                """,
                (venture_id, user["id"])
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Venture not found")

            return VentureResponse(
                id=row[0],
                name=row[1],
                brand_profile=row[2] or {},
                personal_profile=row[3] or {},
                status=row[4],
                workflow_schedule=row[5] or {},
                timezone=row[6],
                tts_voice_id=row[7],
                role=row[8]
            )
    finally:
        db_pool.putconn(conn)


# -----------------------------------------------------------------
#  Update venture
# -----------------------------------------------------------------

@router.patch("/{venture_id}", response_model=VentureResponse)
async def patch_venture(
    venture_id: str, 
    body: VenturePatchRequest, 
    venture: OperatorOnly, 
    db_pool: DBPool
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return VentureResponse(**venture)

    # Convert dicts to JSON for Postgres
    for k in ["brand_profile", "personal_profile", "workflow_schedule"]:
        if k in updates:
            updates[k] = json.dumps(updates[k])

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [venture_id]

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE public.ventures SET {set_clause} WHERE id = %s;", values)
        conn.commit()
    finally:
        db_pool.putconn(conn)
    
    # Sync to disk if relevant fields changed
    if body.brand_profile is not None:
        _write_brand_profile_to_disk(venture_id, body.brand_profile)

    if body.workflow_schedule is not None:
        _write_pipeline_config_to_disk(venture_id, body.workflow_schedule)

    # Update the local 'venture' dict for the response
    venture.update(body.model_dump(exclude_none=True))
    return VentureResponse(**venture)


# -----------------------------------------------------------------
#  Deactivate venture
# -----------------------------------------------------------------

@router.delete("/{venture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_venture(
    venture_id: str,
    venture: OperatorOnly,
    db_pool: DBPool,
):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.ventures SET status = 'archived' WHERE id = %s;",
                (venture_id,),
            )
        conn.commit()
    finally:
        db_pool.putconn(conn)


# -----------------------------------------------------------------
#  Invite team member
# -----------------------------------------------------------------

@router.post("/{venture_id}/members", status_code=status.HTTP_201_CREATED)
async def invite_member(
    venture_id: str,
    body: MemberInviteRequest,
    venture: OperatorOnly,
    db_pool: DBPool,
):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM public.users WHERE email = %s;",
                (body.email,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No user found with email '{body.email}'. They must register first.",
                )
            target_user_id = str(row[0])

            cur.execute("""
                INSERT INTO public.venture_members (user_id, venture_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, venture_id)
                DO UPDATE SET role = EXCLUDED.role;
            """, (target_user_id, venture_id, body.role))
        conn.commit()
    finally:
        db_pool.putconn(conn)

    return {"message": f"'{body.email}' added as {body.role}."}


# -----------------------------------------------------------------
#  Internal helpers
# -----------------------------------------------------------------

def _write_brand_profile_to_disk(venture_id: str, profile: dict):
    from limes_outpost.config import settings
    venture_dir = settings.ventures_dir / venture_id
    venture_dir.mkdir(parents=True, exist_ok=True)
    brand_path = venture_dir / "brand_profile_v1.json"
    brand_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def _write_pipeline_config_to_disk(venture_id: str, workflow_schedule: dict):
    from limes_outpost.config import settings
    config_path = settings.ventures_dir / venture_id / "pipeline_config.json"
    
    # Start with a base or existing config
    config = _DEFAULT_PIPELINE_CONFIG.copy()
    
    # Update enabled flags based on the schedule
    for wf_name, wf_config in workflow_schedule.items():
        if wf_name in config["workflows"]:
            config["workflows"][wf_name]["enabled"] = wf_config.get("enabled", True)
            
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")