"""The feed's message contract.

Every message the provider layer publishes validates against one of these
models. Models forbid unknown fields, so validating a feed also proves that
nothing from the answer key leaked into it. `feed_json_schema()` exports the
contract as JSON Schema for docs/data.md and for consumers in other languages.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# Metres in the absolute frame, with 2 m to spare beyond each line for a ball that has gone out.
X = Annotated[float, Field(ge=-2.0, le=107.0, description="Metres along the pitch, which is 105 m long")]
Y = Annotated[float, Field(ge=-2.0, le=70.0, description="Metres across the pitch, which is 68 m wide")]

PlayPattern = Literal[
    "kick_off", "throw_in", "goal_kick", "corner", "free_kick", "penalty", "drop_ball", "regular_play", "counter"
]


class FreezePlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: str
    team_id: str
    x: X
    y: Y


class FreezeBall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: X
    y: Y
    z: float


class FreezeFrame(BaseModel):
    """Every player on the pitch and the ball at the moment of the event."""

    model_config = ConfigDict(extra="forbid")
    players: list[FreezePlayer]
    ball: FreezeBall


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home: int
    away: int


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feed_version: str
    match_id: str
    seq: int = Field(ge=1, description="Message order in the feed, starting at 1")
    ts: str = Field(description="Wall-clock time the message was published (ISO 8601, UTC)")
    event_id: str = Field(description="Stable ID; an amendment reuses the ID of the event it corrects")
    version: int = Field(ge=1)
    period: int = Field(ge=1, le=2)
    t: float = Field(description="Seconds since the period kicked off")
    clock: float = Field(description="Match clock in seconds; the second half starts at 2700")
    minute: int = Field(description="Broadcast minute: 1-45 or 46-90, staying at 45 or 90 in added time")
    added_minute: int | None = Field(description="Minute of added time, counting from 1")


class OnBall(Base):
    possession: int = Field(description="Possession sequence number")
    team_id: str
    player_id: str
    x: X
    y: Y


class MatchInfo(Base):
    type: Literal["match_info"]
    info: dict[str, Any]


class PeriodStart(Base):
    type: Literal["period_start"]
    possession: int


class PeriodEnd(Base):
    type: Literal["period_end", "match_end"]
    possession: int
    score: Score


class AddedTime(Base):
    type: Literal["added_time"]
    possession: int
    minutes: int


class Pass(OnBall):
    type: Literal["pass"]
    outcome: Literal["complete", "incomplete", "out", "offside"]
    recipient_id: str | None
    height: Literal["ground", "high"]
    pass_type: Literal["open_play", "kick_off", "throw_in", "goal_kick", "corner", "free_kick"]
    body_part: Literal["foot", "head", "hands"]
    cross: bool
    through_ball: bool
    length: float
    speed_kmh: float
    under_pressure: bool
    end_x: X
    end_y: Y
    freeze_frame: FreezeFrame | None = Field(
        default=None,
        description=(
            "Everyone's position as the ball was played, when the player it was meant for was in an offside "
            "position and went for it. Offside flags and VAR offside checks point to this pass."
        ),
    )


class Carry(OnBall):
    type: Literal["carry"]
    end_x: X
    end_y: Y
    duration: float


class Pressure(OnBall):
    type: Literal["pressure"]
    target_id: str


class Tackle(OnBall):
    type: Literal["tackle"]
    opponent_id: str
    outcome: Literal["won", "lost"]


class Simple(OnBall):
    type: Literal["interception", "ball_recovery", "block", "woodwork", "injury"]


class Duel(OnBall):
    type: Literal["duel"]
    opponent_id: str
    duel_type: Literal["aerial", "ground"]
    outcome: Literal["won"]


class Clearance(OnBall):
    type: Literal["clearance"]
    body_part: Literal["foot", "head"]
    end_x: X
    end_y: Y


ShotType = Annotated[
    Literal["open_play", "free_kick", "penalty"],
    Field(description="Penalty, direct free kick or anything else; where the move began is in play_pattern"),
]


class Shot(OnBall):
    type: Literal["shot"]
    outcome: Literal["goal", "saved", "off_target", "blocked"]
    body_part: Literal["right_foot", "left_foot", "head"]
    shot_type: ShotType
    play_pattern: PlayPattern = Field(description="How the possession began")
    set_piece: bool
    speed_kmh: float
    distance: float
    goalkeeper_id: str
    end_x: X
    end_y: Y
    end_z: float
    freeze_frame: FreezeFrame


class Goalkeeper(OnBall):
    type: Literal["goalkeeper"]
    action: Literal["save", "claim"]
    outcome: Literal["held", "parried"]


class Goal(Base):
    type: Literal["goal"]
    possession: int
    team_id: str = Field(description="The team credited with the goal")
    player_id: str = Field(description="The scorer; for an own goal, the defender who put it in")
    assist_id: str | None
    own_goal: bool
    score: Score
    from_event_id: str = Field(description="The shot the goal came from; for an own goal headed in, the cross")
    shot_type: ShotType
    play_pattern: PlayPattern = Field(description="How the possession began")
    set_piece: bool
    header: bool = Field(description="Whether the scorer's touch was a header, own goals included")


class Foul(OnBall):
    type: Literal["foul"]
    fouled_id: str | None
    foul_type: Literal["challenge", "aerial", "handball"]
    advantage: bool
    penalty: bool
    card: Literal["yellow", "red"] | None
    freeze_frame: FreezeFrame | None = None


class Card(Base):
    type: Literal["card"]
    possession: int
    team_id: str
    player_id: str
    card: Literal["yellow", "second_yellow", "red"]
    reason: Literal["foul", "handball", "dissent"]


class Offside(OnBall):
    """The flag. x and y are where the player was when the pass was played; the pass
    (pass_event_id) carries the freeze frame offside is judged on."""

    type: Literal["offside"]
    pass_event_id: str
    delayed_flag: bool


class BallOut(Base):
    type: Literal["ball_out"]
    possession: int
    restart: Literal["throw_in", "goal_kick", "corner"]
    last_touch_team_id: str
    x: X
    y: Y


class Substitution(Base):
    type: Literal["substitution"]
    possession: int
    team_id: str
    player_off_id: str
    player_on_id: str
    half_time: bool
    reason: str | None = None


class VarCheck(Base):
    type: Literal["var_check"]
    possession: int
    status: Literal["started", "complete"]
    check: Literal["goal", "penalty"]
    incident: Literal["offside", "handball", "foul"]
    subject_id: str
    x: X
    y: Y
    on_field_decision: Literal["goal", "penalty", "no_penalty"] | None = None
    decision: Literal["goal", "no_goal", "penalty", "no_penalty"] | None = None
    overturned: bool | None = None
    on_field_review: bool | None = None
    related_event_id: str | None = None
    goal_event_id: str | None = None
    pass_event_id: str | None = None
    score: Score | None = None
    freeze_frame: FreezeFrame | None = None


class PossessionChange(Base):
    type: Literal["possession_change"]
    possession: int
    team_id: str
    from_team_id: str
    cause: str
    x: X
    y: Y


class Amendment(Base):
    """A correction. corrected_event is the event as it should have been; changes lists what moved.

    The clock stops at each whistle: an amendment issued at half-time or after the match carries the
    clock of the whistle before it, and ts says when it was issued.
    """

    type: Literal["amendment"]
    amends: str
    changes: dict[str, dict[str, Any]]
    reason: str
    corrected_event: dict[str, Any]


FeedMessage = Annotated[
    MatchInfo
    | PeriodStart
    | PeriodEnd
    | AddedTime
    | Pass
    | Carry
    | Pressure
    | Tackle
    | Simple
    | Duel
    | Clearance
    | Shot
    | Goalkeeper
    | Goal
    | Foul
    | Card
    | Offside
    | BallOut
    | Substitution
    | VarCheck
    | PossessionChange
    | Amendment,
    Field(discriminator="type"),
]

FEED_ADAPTER: TypeAdapter[Any] = TypeAdapter(FeedMessage)


def validate_message(message: dict) -> BaseModel:
    return FEED_ADAPTER.validate_python(message)


def feed_json_schema() -> dict:
    return FEED_ADAPTER.json_schema()
