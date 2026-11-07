from dataclasses import FrozenInstanceError, replace

import pytest

from umbod.core.persistence import (
    NonReusingIntegerKeyCodec,
)
from tests.support.persistence_contracts import (
    GeneratedKey,
    generated_table,
    non_reusing_generated_table,
)


@pytest.mark.parametrize("variant", ("zero", "multiple", "noninteger"))
def test_non_reusing_integer_key_codec_rejects_invalid_fields(variant: str) -> None:
    table, _ = generated_table()
    fields = {
        "zero": (),
        "multiple": table.row_codec.fields,
        "noninteger": (table.row_codec.fields[1],),
    }[variant]
    with pytest.raises(ValueError, match="key field"):
        NonReusingIntegerKeyCodec(GeneratedKey, fields)


def test_non_reusing_descriptors_are_immutable_and_policy_specific() -> None:
    ordinary, _ = generated_table("same_samples")
    opted_in, _ = non_reusing_generated_table("same_samples")
    equivalent, _ = non_reusing_generated_table("same_samples")
    assert opted_in == equivalent
    assert opted_in.key_codec == equivalent.key_codec
    assert ordinary != opted_in
    assert ordinary.key_codec != opted_in.key_codec
    assert opted_in.key_codec != ordinary.key_codec
    with pytest.raises(FrozenInstanceError):
        setattr(opted_in.key_codec, "fields", ())
    assert replace(opted_in.key_codec) == opted_in.key_codec
