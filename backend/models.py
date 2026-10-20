from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerProfile:
    name: str
    email: str
    email_verified: bool
    avatar: str | None
    record: int
    matches_played: int
    wins: int
    losses: int
    draws: int
    ranking: int | None
    achievements: tuple[str, ...]
    match_history: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "email": self.email,
            "verificado": self.email_verified,
            "avatar": self.avatar,
            "record": self.record,
            "statistics": {
                "matches_played": self.matches_played,
                "wins": self.wins,
                "losses": self.losses,
                "draws": self.draws,
            },
            "ranking": self.ranking,
            "achievements": list(self.achievements),
            "match_history": list(self.match_history),
        }


@dataclass(frozen=True)
class RegistrationResult:
    profile: PlayerProfile
    verification_sent: bool
    email_error: str
