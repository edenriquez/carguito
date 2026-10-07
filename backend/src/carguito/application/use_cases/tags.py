from __future__ import annotations

from uuid import UUID

from ...domain.entities import Tag, slugify
from ..ports.outbound import CubeWriter, TagRepository, TransactionRepository
from .update_transaction import TransactionNotFoundError

#: Same sentinel discipline as the transaction patch: an absent key means
#: "leave it alone", ``null`` means "clear it".
UNSET = object()


class TagNotFoundError(Exception):
    """Raised when a tag does not exist or belongs to another user."""


class ManageTagsUseCase:
    """Tag CRUD and the tagging operations, with the cube kept in step.

    The relational ``tags`` / ``transaction_tags`` pair is the record of truth.
    Everything this writes to the cube -- ``fact_transactions.tag_ids``, the
    bridge, ``dim_tag`` -- is derived and reproducible by
    :class:`RebuildCubeUseCase`. It is written eagerly anyway because a tag the
    user just applied has to show up in the totals on the next render.

    Every read starts from the tag's or transaction's owner. A tag belonging to
    someone else is reported as missing rather than forbidden, so the response
    never confirms that an id exists -- the same non-disclosure pattern as
    ``ManageStatementsUseCase.delete``.
    """

    def __init__(
        self,
        *,
        tags: TagRepository,
        transactions: TransactionRepository,
        cube: CubeWriter,
    ) -> None:
        self._tags = tags
        self._transactions = transactions
        self._cube = cube

    # --- CRUD ------------------------------------------------------------
    def list(self, *, user_id: UUID) -> list[Tag]:
        return self._tags.list_for_user(user_id)

    def create(
        self, *, user_id: UUID, name: str, color: str | None = None, kind: str = "plain"
    ) -> Tag:
        tag = Tag(user_id=user_id, name=name, color=color, kind=kind)  # type: ignore[arg-type]
        self._tags.add(tag)
        self._cube.sync_tags([tag])
        return tag

    def update(
        self,
        *,
        user_id: UUID,
        tag_id: UUID,
        name=UNSET,
        color=UNSET,
        kind=UNSET,
    ) -> Tag:
        tag = self._owned(user_id, tag_id)
        if name is not UNSET:
            tag.name = str(name).strip()
            if not tag.name:
                raise ValueError("Tag name must not be empty.")
            # The slug follows the name. Leaving it behind would make the
            # uniqueness rule describe a name nobody can see any more.
            tag.slug = slugify(tag.name)
        if color is not UNSET:
            tag.color = color
        if kind is not UNSET:
            if kind not in ("plain", "investment"):
                raise ValueError(f"Unknown tag kind {kind!r}; expected 'plain' or 'investment'.")
            tag.kind = kind

        self._tags.update(tag)
        self._cube.sync_tags([tag])
        return tag

    def delete(self, *, user_id: UUID, tag_id: UUID) -> int:
        """Remove a tag. Returns how many transactions lost it.

        The transactions themselves survive -- a tag is an annotation, and
        deleting the annotation is not deleting the money.
        """
        self._owned(user_id, tag_id)
        affected = self._tags.transaction_ids_for_tag(tag_id)
        self._tags.delete(tag_id)
        self._cube.forget_tag(tag_id)
        self._refresh_cube(user_id, affected)
        return len(affected)

    # --- tagging ---------------------------------------------------------
    def set_for_transaction(
        self, *, user_id: UUID, transaction_id: UUID, tag_ids: list[UUID]
    ) -> list[UUID]:
        """Replace one transaction's tag list. Returns the tags now attached."""
        transaction = self._transactions.get(transaction_id)
        if transaction is None or transaction.user_id != user_id:
            raise TransactionNotFoundError(str(transaction_id))
        for tag_id in tag_ids:
            self._owned(user_id, tag_id)

        self._tags.replace_for_transaction(transaction_id, tag_ids)
        self._refresh_cube(user_id, [transaction_id])
        return list(dict.fromkeys(tag_ids))

    def attach_to_transactions(
        self, *, user_id: UUID, tag_id: UUID, transaction_ids: list[UUID]
    ) -> int:
        """Bulk-tag. Returns how many of the requested transactions were reached.

        Ids the user does not own simply do not come back from the repository,
        so they are silently not tagged rather than 404-ing the whole batch: the
        caller learns how many landed, not which ids exist.
        """
        self._owned(user_id, tag_id)
        owned = [t.id for t in self._transactions.list_by_ids(user_id, transaction_ids)]
        self._tags.attach_to_transactions(tag_id, owned)
        self._refresh_cube(user_id, owned)
        return len(owned)

    # --- internals -------------------------------------------------------
    def _owned(self, user_id: UUID, tag_id: UUID) -> Tag:
        tag = self._tags.get(tag_id)
        if tag is None or tag.user_id != user_id:
            raise TagNotFoundError(str(tag_id))
        return tag

    def _refresh_cube(self, user_id: UUID, transaction_ids: list[UUID]) -> None:
        """Re-derive the fact rows whose tag list just changed.

        Re-read rather than patched in memory: the repository is what knows the
        post-write tag list, and reproducing that reasoning here is how the two
        copies start disagreeing.
        """
        if not transaction_ids:
            return
        self._cube.upsert_transactions(
            self._transactions.list_by_ids(user_id, transaction_ids)
        )
