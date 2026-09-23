"""The single inventory table.

Column widths are deliberate: 45 characters fits an IPv6 address with an
embedded IPv4 suffix, which is the longest mgmt_ip a device can carry.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mgmt_ip: Mapped[str] = mapped_column(String(45))
    vendor: Mapped[str] = mapped_column(String(64), default="cisco")
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    site: Mapped[str | None] = mapped_column(String(128), default=None)
    role: Mapped[str] = mapped_column(String(64), default="router")
