from collections.abc import Mapping, Sequence


class JsonPointerResolutionError(ValueError):
    pass


class SameDocumentJsonPointerResolver:
    def __init__(self, document: object, maximum_depth: int) -> None:
        self._document = document
        self._maximum_depth = maximum_depth

    def resolve(self, reference: str) -> object:
        return self._resolve(reference, (), 0)

    def _resolve(self, reference: str, active: tuple[str, ...], depth: int) -> object:
        if not reference.startswith("#"):
            raise JsonPointerResolutionError("External references are unsupported")
        if depth >= self._maximum_depth:
            raise JsonPointerResolutionError("Reference depth limit exceeded")
        if reference in active:
            raise JsonPointerResolutionError("Reference cycle detected")
        fragment = reference[1:]
        if fragment == "":
            target = self._document
        elif fragment.startswith("/"):
            target = self._walk(fragment)
        else:
            raise JsonPointerResolutionError("Reference must use a JSON Pointer fragment")
        if isinstance(target, Mapping) and isinstance(target.get("$ref"), str):
            resolved = self._resolve(target["$ref"], (*active, reference), depth + 1)
            return self._merge(resolved, target)
        return target

    def _walk(self, pointer: str) -> object:
        current = self._document
        for encoded_token in pointer[1:].split("/"):
            token = self._decode_token(encoded_token)
            if isinstance(current, Mapping) and token in current:
                current = current[token]
            elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
                try:
                    current = current[int(token)]
                except (ValueError, IndexError) as error:
                    raise JsonPointerResolutionError(
                        f"JSON Pointer target is missing: {pointer}"
                    ) from error
            else:
                raise JsonPointerResolutionError(f"JSON Pointer target is missing: {pointer}")
        return current

    def _decode_token(self, token: str) -> str:
        result = ""
        index = 0
        while index < len(token):
            if token[index] != "~":
                result += token[index]
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in ("0", "1"):
                raise JsonPointerResolutionError("JSON Pointer contains invalid token escaping")
            result += "~" if token[index + 1] == "0" else "/"
            index += 2
        return result

    def _merge(self, resolved: object, reference_object: Mapping[object, object]) -> object:
        siblings = {key: value for key, value in reference_object.items() if key != "$ref"}
        if not siblings:
            return resolved
        if not isinstance(resolved, Mapping):
            raise JsonPointerResolutionError("Reference siblings require an object target")
        return {**resolved, **siblings}
