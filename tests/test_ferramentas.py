from app.ferramentas import DECLARACOES


def test_nomes_unicos_e_com_descricao():
    nomes = [d["name"] for d in DECLARACOES]
    assert len(nomes) == len(set(nomes)) == 14
    assert all(d["description"] for d in DECLARACOES)


def test_campos_obrigatorios_existem_nas_propriedades():
    for declaracao in DECLARACOES:
        parametros = declaracao.get("parameters")
        if parametros:
            assert set(parametros.get("required", [])) <= set(parametros["properties"]), declaracao["name"]
