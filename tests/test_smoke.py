"""Smoke tests do scaffold — garantem que o pacote importa e a versão está exposta."""


def test_versao_exposta():
    import uau_extractor

    assert uau_extractor.__version__ == "0.1.0"


def test_modulos_importam():
    import uau_extractor.client  # noqa: F401
    import uau_extractor.config  # noqa: F401
    import uau_extractor.db  # noqa: F401
    import uau_extractor.extractors  # noqa: F401
    import uau_extractor.ingestao  # noqa: F401
    import uau_extractor.storage  # noqa: F401
    import uau_extractor.transforms  # noqa: F401
