"""UI strings and language detection.

The language comes from the `nono_lang` cookie, which is only set when the player
picks one; otherwise from the browser's Accept-Language header.
"""

from fastapi import Request

LANGS = {"en": "English", "pt-BR": "Português"}
DEFAULT = "en"
COOKIE = "nono_lang"

# Values may contain trusted HTML (rendered with |safe). "{n}"-style placeholders are filled in JS.
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "description": "A new nonogram every day.",
        "today_link": "Nono, today's puzzle",
        "past_puzzles": "Past puzzles",
        "mute": "Mute sounds",
        "unmute": "Unmute sounds",
        "how_to_play": "How to play",
        "language": "Language",
        "step_clues": "The numbers beside each row and above each column are the lengths of its filled runs, in order. "
        "Runs are separated by at least one empty square.",
        "step_controls": "Tap a square to fill it. Switch to <b>Mark</b>, or right-click, to cross out squares you know "
        "are empty. Drag to paint a whole line at once.",
        "step_lives": 'Every move is checked. A wrong one costs a <span class="heart">♥</span> and shows the real square. '
        "You get 3 for a 5×5 puzzle and 5 for a 10×10. Lose them all and the puzzle is over.",
        "step_fills": "Only the filled squares count: crosses just help you think. Clue numbers fade once they're done.",
        "step_daily": "There's a new puzzle every day, and you can play the ones you missed from the calendar.",
        "lets_play": "Let's play",
        "prev_month": "Previous month",
        "next_month": "Next month",
        "won": "Solved",
        "lost": "Failed",
        "playing": "In progress",
        "not_played": "Not played",
        "fill": "Fill",
        "mark": "Mark",
        "mark_with_x": "Mark with X",
        "lives_left": "{n} of {max} lives left",
        "easy": "Easy",
        "medium": "Medium",
        "hard": "Hard",
        "solved_title": "Solved!",
        "out_of_lives": "Out of lives",
        "next_puzzle": "Next puzzle in",
        "share": "Share",
        "copied": "Copied!",
    },
    "pt-BR": {
        "description": "Um nonograma novo todo dia.",
        "today_link": "Nono, desafio de hoje",
        "past_puzzles": "Desafios anteriores",
        "mute": "Desativar sons",
        "unmute": "Ativar sons",
        "how_to_play": "Como jogar",
        "language": "Idioma",
        "step_clues": "Os números ao lado de cada linha e acima de cada coluna são os tamanhos dos blocos pintados, "
        "em ordem. Os blocos são separados por pelo menos um quadrado vazio.",
        "step_controls": "Toque em um quadrado para pintá-lo. Mude para <b>Marcar</b>, ou use o botão direito, para "
        "riscar quadrados que você sabe que estão vazios. Arraste para pintar uma linha inteira de uma vez.",
        "step_lives": 'Toda jogada é conferida. Um erro custa um <span class="heart">♥</span> e revela o quadrado certo. '
        "São 3 vidas no 5×5 e 5 no 10×10. Perdeu todas, acabou o desafio.",
        "step_fills": "Só os quadrados pintados contam: os X só ajudam a pensar. "
        "Os números das dicas se apagam quando concluídos.",
        "step_daily": "Todo dia tem um desafio novo, e dá para jogar os que você perdeu pelo calendário.",
        "lets_play": "Vamos jogar",
        "prev_month": "Mês anterior",
        "next_month": "Próximo mês",
        "won": "Resolvido",
        "lost": "Falhou",
        "playing": "Em andamento",
        "not_played": "Não jogado",
        "fill": "Pintar",
        "mark": "Marcar",
        "mark_with_x": "Marcar com X",
        "lives_left": "{n} de {max} vidas restantes",
        "easy": "Fácil",
        "medium": "Médio",
        "hard": "Difícil",
        "solved_title": "Resolvido!",
        "out_of_lives": "Sem vidas",
        "next_puzzle": "Próximo desafio em",
        "share": "Compartilhar",
        "copied": "Copiado!",
    },
}

assert all(STRINGS[lang].keys() == STRINGS[DEFAULT].keys() for lang in LANGS), "every language needs every key"


def _match(tag: str) -> str | None:
    tag = tag.strip().lower()
    for lang in LANGS:  # "pt", "pt-PT" and "pt-BR" all get Brazilian Portuguese for now
        if tag == lang.lower() or tag.split("-")[0] == lang.lower().split("-")[0]:
            return lang
    return None


def from_accept_language(header: str) -> str:
    """Best supported language from an Accept-Language header, honouring q-values."""
    tags = []
    for i, part in enumerate(header.split(",")):
        tag, _, params = part.partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        tags.append((-q, i, tag))
    for _, _, tag in sorted(tags):
        if lang := _match(tag):
            return lang
    return DEFAULT


def pick(request: Request) -> str:
    if (cookie := request.cookies.get(COOKIE)) in LANGS:
        return cookie
    return from_accept_language(request.headers.get("accept-language", ""))
