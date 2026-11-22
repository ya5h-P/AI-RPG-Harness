import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import urllib.request

import harness
import server


class TestHarness(unittest.TestCase):
    def test_format_player_text_modes(self):
        self.assertEqual(harness.format_player_text("say", "hello there"), 'You say, "hello there"')
        self.assertEqual(harness.format_player_text("say", '"Already quoted"'), 'You say, "Already quoted"')
        self.assertEqual(harness.format_player_text("do", "pick up a bucket"), "You pick up a bucket.")
        self.assertEqual(harness.format_player_text("do", "Open the door!"), "You open the door!")
        self.assertEqual(harness.format_player_text("do", "you look around"), "You look around.")
        self.assertEqual(harness.format_player_text("do", "i look around"), "You look around.")
        self.assertEqual(harness.format_player_text("do", "I'm checking my pockets"), "You're checking your pockets.")
        self.assertEqual(harness.format_player_text("do", "I am bracing myself"), "You are bracing yourself.")
        self.assertEqual(
            harness.format_player_text("story", "A cold wind blows across the hall."),
            "A cold wind blows across the hall.",
        )

    def test_format_player_text_third_person(self):
        self.assertEqual(
            harness.format_player_text("say", "hello", third_person=True, character_name="Kael"),
            'Kael says, "hello"',
        )
        self.assertEqual(
            harness.format_player_text("say", "hello", third_person=True, character_name=""),
            'They say, "hello"',
        )
        self.assertEqual(
            harness.format_player_text("do", "i look around", third_person=True, character_name="Kael"),
            "Kael look around.",
        )
        self.assertEqual(
            harness.format_player_text("do", "picks up a bucket", third_person=True, character_name="Kael"),
            "Kael picks up a bucket.",
        )

    def test_build_chat_messages_alternates_roles(self):
        story = harness.Story(
            id="s1",
            title="Test",
            ai_instructions="Custom GM instructions.",
            story_summary="You entered the cave.",
            plot_essentials="You carry a lantern.",
            authors_note="Use 17th century language.",
            segments=[
                harness.Segment(id="1", kind="opening", text="Darkness surrounds you."),
                harness.Segment(id="2", kind="do", text="You light the lantern."),
                harness.Segment(id="3", kind="ai", text="Warm amber light fills the cave."),
                harness.Segment(id="4", kind="story", text="A distant drip echoes."),
                harness.Segment(id="5", kind="say", text='You say, "Hello?"'),
            ],
        )
        msgs = harness.build_chat_messages(story)
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "user"])
        self.assertIn("Custom GM instructions.", msgs[0]["content"])
        self.assertIn("You entered the cave.", msgs[0]["content"])
        self.assertIn("You carry a lantern.", msgs[0]["content"])
        self.assertIn("Darkness surrounds you.", msgs[1]["content"])
        self.assertIn("You light the lantern.", msgs[1]["content"])
        self.assertEqual(msgs[2]["content"], "Warm amber light fills the cave.")
        self.assertIn("A distant drip echoes.", msgs[3]["content"])
        self.assertIn('You say, "Hello?"', msgs[3]["content"])
        self.assertIn("Use 17th century language.", msgs[3]["content"])

    def test_build_chat_messages_back_to_back_ai_continue(self):
        story = harness.Story(
            id="s2",
            title="Test2",
            segments=[
                harness.Segment(id="1", kind="opening", text="Scene."),
                harness.Segment(id="2", kind="ai", text="First beat."),
                harness.Segment(id="3", kind="ai", text="Second beat."),
            ],
        )
        msgs = harness.build_chat_messages(story)
        self.assertEqual(
            [m["role"] for m in msgs],
            ["system", "user", "assistant", "user", "assistant", "user"],
        )


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.orig_stories_dir = harness.STORIES_DIR
        self.orig_scenarios_dir = harness.SCENARIOS_DIR
        self.orig_scripts_dir = harness.SCRIPTS_DIR
        harness.STORIES_DIR = Path(self.tmp.name) / "stories"
        harness.SCENARIOS_DIR = Path(self.tmp.name) / "scenarios"
        harness.SCRIPTS_DIR = Path(self.tmp.name) / "scripts"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.RPGRequestHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        harness.STORIES_DIR = self.orig_stories_dir
        harness.SCENARIOS_DIR = self.orig_scenarios_dir
        harness.SCRIPTS_DIR = self.orig_scripts_dir
        self.tmp.cleanup()

    def _req(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_scenario_selection_creation_and_fixed_opening(self):
        # Starter scenarios seeded, zero stories initially
        st, sc_list = self._req("GET", "/api/scenarios")
        self.assertEqual(st, 200)
        self.assertGreaterEqual(len(sc_list["scenarios"]), 2)

        st, stories_list = self._req("GET", "/api/stories")
        self.assertEqual(st, 200)
        self.assertEqual(stories_list["stories"], [])

        # Create a custom scenario with name + fixed opening
        st, created = self._req(
            "POST",
            "/api/scenarios",
            {"name": "Clockwork Spire", "opening": "Brass gears hum beneath your boots."},
        )
        self.assertEqual(st, 201)
        sc_id = created["scenario"]["id"]

        # Update scenario
        st, updated = self._req(
            "PATCH",
            f"/api/scenarios/{sc_id}",
            {"name": "Clockwork Spire II"},
        )
        self.assertEqual(st, 200)
        self.assertEqual(updated["scenario"]["name"], "Clockwork Spire II")

        # Start story from scenario -> fixed opening is first segment
        st, story_res = self._req("POST", "/api/stories", {"scenario_id": sc_id})
        self.assertEqual(st, 201)
        story = story_res["story"]
        self.assertEqual(story["title"], "Clockwork Spire II")
        self.assertEqual(story["segments"][0]["kind"], "opening")
        self.assertEqual(story["segments"][0]["text"], "Brass gears hum beneath your boots.")

        # Undo stops when no undo snapshot exists (just started from scenario)
        st, undo_res = self._req("POST", f"/api/stories/{story['id']}/undo", {})
        self.assertEqual(st, 200)
        self.assertFalse(undo_res["undone"])
        self.assertEqual(len(undo_res["story"]["segments"]), 1)

        # Delete scenario
        st, del_res = self._req("DELETE", f"/api/scenarios/{sc_id}")
        self.assertEqual(st, 200)
        self.assertTrue(del_res["deleted"])

    def test_story_crud_and_3_modes(self):
        st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        self.assertEqual(st, 201)
        story_id = created["story"]["id"]

        for mode, raw, expected in [
            ("say", "hello", 'You say, "hello"'),
            ("do", "pick up a bucket", "You pick up a bucket."),
            ("story", "The lantern flickers.", "The lantern flickers."),
        ]:
            st, res = self._req(
                "POST",
                f"/api/stories/{story_id}/append",
                {"mode": mode, "text": raw},
            )
            self.assertEqual(st, 200)
            self.assertEqual(res["segment"]["text"], expected)
            self.assertEqual(res["segment"]["kind"], mode)

        st, undo_res = self._req("POST", f"/api/stories/{story_id}/undo", {})
        self.assertEqual(st, 200)
        self.assertTrue(undo_res["undone"])
        self.assertEqual(len(undo_res["story"]["segments"]), 3)

    def test_generate_sse_streaming_with_mock_llm(self):
        captured_payloads = []

        class MockLLMHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                captured_payloads.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunks = [
                    {"choices": [{"delta": {"content": "The bucket "}}]},
                    {"choices": [{"delta": {"content": "clatters loudly."}}]},
                ]
                for c in chunks:
                    self.wfile.write(f"data: {json.dumps(c)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        mock_llm = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        mock_port = mock_llm.server_address[1]
        mock_thread = threading.Thread(target=mock_llm.serve_forever, daemon=True)
        mock_thread.start()
        orig_llm_url = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{mock_port}"

        try:
            _, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            story_id = created["story"]["id"]

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"mode": "do", "text": "kick the bucket"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_sse = resp.read().decode("utf-8")

            self.assertEqual(
                captured_payloads[0]["chat_template_kwargs"],
                {"enable_thinking": False},
            )
            self.assertIn("event: user_segment", raw_sse)
            self.assertIn("You kick the bucket.", raw_sse)
            self.assertIn("event: token", raw_sse)
            self.assertIn("The bucket ", raw_sse)
            self.assertIn("event: done", raw_sse)

            _, updated = self._req("GET", f"/api/stories/{story_id}")
            kinds = [s["kind"] for s in updated["story"]["segments"]]
            self.assertEqual(kinds[-2:], ["do", "ai"])
            self.assertEqual(updated["story"]["segments"][-1]["text"], "The bucket clatters loudly.")
        finally:
            server.LLM_URL = orig_llm_url
            mock_llm.shutdown()
            mock_llm.server_close()

    def test_story_cards_trigger_and_context_viewer(self):
        _, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        story_id = created["story"]["id"]

        cards = [
            {
                "id": "c1",
                "title": "Wooden Bucket",
                "card_type": "Item",
                "keys": "bucket, pail",
                "entry": "A sturdy oak bucket bound with iron hoops.",
            },
            {
                "id": "c2",
                "title": "Silver Dragon",
                "card_type": "Character",
                "keys": "dragon, wyrm",
                "entry": "A slumbering silver dragon beneath the mountain.",
            },
        ]
        st, patched = self._req(
            "PATCH",
            f"/api/stories/{story_id}",
            {
                "story_cards": cards,
                "authors_note": "Keep prose tense and atmospheric.",
            },
        )
        self.assertEqual(st, 200)
        self.assertEqual(len(patched["story"]["story_cards"]), 2)

        # The Rusty Lantern opening mentions "bucket" -> c1 triggers, c2 does not
        # AI only sees the entry description, not the player-facing title.
        st, ctx = self._req("GET", f"/api/stories/{story_id}/context")
        self.assertEqual(st, 200)
        triggered_titles = [c["title"] for c in ctx["triggered_cards"]]
        self.assertEqual(triggered_titles, ["Wooden Bucket"])
        self.assertGreater(ctx["total_tokens"], 0)
        self.assertIn("A sturdy oak bucket bound with iron hoops.", ctx["messages"][-1]["content"])
        self.assertNotIn("Wooden Bucket", ctx["messages"][-1]["content"])
        self.assertIn("Keep prose tense and atmospheric.", ctx["messages"][-1]["content"])

    def test_placeholders_multiple_choice_and_character_creator(self):
        # 1. Story scenario with case-sensitive placeholders and ${character.name}
        st, sc_res = self._req(
            "POST",
            "/api/scenarios",
            {
                "name": "Kingdom Gate",
                "scenario_type": "story",
                "opening": "You are ${character.name}, ${role} from ${Role}. Hail ${character.name}!",
                "plot_essentials": "${character.name} serves ${Role}.",
                "third_person": True,
                "story_cards": [
                    {
                        "id": "card1",
                        "title": "${character.name}'s Crest",
                        "card_type": "Item",
                        "keys": "${character.name}",
                        "entry": "${character.name} wears the crest of ${Role}.",
                    }
                ],
            },
        )
        self.assertEqual(st, 201)
        sc_id = sc_res["scenario"]["id"]

        st, play_res = self._req(
            "POST",
            "/api/stories",
            {
                "scenario_id": sc_id,
                "placeholder_answers": {
                    "character.name": "Peach",
                    "role": "a princess",
                    "Role": "Larion",
                },
            },
        )
        self.assertEqual(st, 201)
        story = play_res["story"]
        self.assertEqual(story["character_name"], "Peach")
        self.assertEqual(
            story["segments"][0]["text"],
            "You are Peach, a princess from Larion. Hail Peach!",
        )
        self.assertEqual(story["plot_essentials"], "Peach serves Larion.")
        self.assertEqual(story["story_cards"][0]["title"], "Peach's Crest")
        self.assertEqual(story["story_cards"][0]["entry"], "Peach wears the crest of Larion.")

        # 2. Multiple Choice scenario
        st, mc_res = self._req(
            "POST",
            "/api/scenarios",
            {
                "name": "Night Hunt",
                "scenario_type": "multiple_choice",
                "choices": [
                    {"id": "vamp", "label": "Vampire", "opening": "You awaken in a velvet coffin."},
                    {"id": "hunt", "label": "Hunter", "opening": "You check your silver bolts."},
                ],
            },
        )
        self.assertEqual(st, 201)
        st, mc_play = self._req(
            "POST",
            "/api/stories",
            {"scenario_id": mc_res["scenario"]["id"], "choice_id": "hunt"},
        )
        self.assertEqual(st, 201)
        self.assertEqual(mc_play["story"]["segments"][0]["text"], "You check your silver bolts.")

        # 3. Character Creator scenario (no fixed opening; selected cards populate Plot Essentials)
        st, cc_res = self._req(
            "POST",
            "/api/scenarios",
            {
                "name": "Faerun",
                "scenario_type": "character_creator",
                "story_cards": [
                    {"id": "orc", "title": "Orc", "card_type": "Character", "keys": "orc", "entry": "You are a towering Orc warrior."},
                    {"id": "elf", "title": "Elf", "card_type": "Character", "keys": "elf", "entry": "You are a sharp-eyed Elf."},
                ],
            },
        )
        self.assertEqual(st, 201)
        st, cc_play = self._req(
            "POST",
            "/api/stories",
            {"scenario_id": cc_res["scenario"]["id"], "selected_card_ids": ["orc"]},
        )
        self.assertEqual(st, 201)
        self.assertEqual(cc_play["story"]["segments"], [])
        self.assertIn("towering Orc warrior", cc_play["story"]["plot_essentials"])

    def test_scripting_hooks_state_and_reusable_scripts(self):
        # 1. Create a reusable script via API
        input_code = """
        const modifier = (text) => {
          if (text.includes('grab a sword')) {
            state.items = ['sword'];
            state.memory = { context: 'You have a sword.' };
            state.message = 'You got a sword!';
            addStoryCard('sword', 'A gleaming iron sword.', 'Item', 'Iron Sword');
            console.log('Added sword');
            return { text: text + '\\nYou also now have a sword!' };
          }
          if (text.includes(':status')) {
            state.message = 'Status OK';
            return { text: null, stop: true };
          }
          return { text };
        };
        modifier(text);
        """
        output_code = """
        const modifier = (text) => ({ text: text.replace(/ not /gi, ' ') });
        modifier(text);
        """
        st, sc_res = self._req(
            "POST",
            "/api/scripts",
            {
                "name": "Sword & Cleanse",
                "description": "Adds sword and removes 'not'.",
                "input": input_code,
                "output": output_code,
            },
        )
        self.assertEqual(st, 201)
        script_id = sc_res["script"]["id"]

        # 2. Test /api/scripts/test sandbox
        st, test_res = self._req(
            "POST",
            "/api/scripts/test",
            {"hook": "input", "code": input_code, "text": "You grab a sword."},
        )
        self.assertEqual(st, 200)
        self.assertTrue(test_res["ok"])
        self.assertIn("You also now have a sword!", test_res["text"])
        self.assertEqual(test_res["state"]["message"], "You got a sword!")
        self.assertEqual(len(test_res["storyCards"]), 1)

        # 3. Attach script to a Story and run input hook + stop + output hook
        _, story_res = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        story_id = story_res["story"]["id"]
        self._req(
            "PATCH",
            f"/api/stories/{story_id}",
            {"attached_scripts": [{"script_id": script_id, "enabled": True}]},
        )

        # Input hook mutates text, state, story_cards, and logs
        st, app_res = self._req(
            "POST",
            f"/api/stories/{story_id}/append",
            {"mode": "do", "text": "grab a sword"},
        )
        self.assertEqual(st, 200)
        self.assertIn("You also now have a sword!", app_res["segment"]["text"])
        self.assertEqual(app_res["story"]["script_state"]["message"], "You got a sword!")
        self.assertEqual(app_res["story"]["story_cards"][0]["title"], "Iron Sword")

        # state.memory.context overrides Plot Essentials in Context Viewer
        st, ctx = self._req("GET", f"/api/stories/{story_id}/context")
        self.assertEqual(ctx["sections"][2]["text"], "You have a sword.")

        # Stop: true via :status does not add a segment or call LLM
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
            data=json.dumps({"mode": "do", "text": ":status"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw_sse = resp.read().decode("utf-8")
        self.assertNotIn("event: user_segment", raw_sse)
        self.assertIn("Status OK", raw_sse)

        # Mock LLM to verify output modifier runs on AI output
        class MockLLMHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunk = {"choices": [{"delta": {"content": "You are not afraid."}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        mock_llm = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        mock_thread = threading.Thread(target=mock_llm.serve_forever, daemon=True)
        mock_thread.start()
        orig_llm_url = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{mock_llm.server_address[1]}"
        try:
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                resp.read()
            _, final_story = self._req("GET", f"/api/stories/{story_id}")
            self.assertEqual(final_story["story"]["segments"][-1]["text"], "You are afraid.")
        finally:
            server.LLM_URL = orig_llm_url
            mock_llm.shutdown()
            mock_llm.server_close()

    def test_import_aidungeon_metadata_json(self):
        raw = {
            "exportedAt": "2026-01-01T00:00:00.000Z",
            "adventure": {
                "title": "Republic City Tales",
                "description": "An episodic elemental city adventure.",
                "memory": "Republic City blends four elemental traditions.",
                "authorsNote": "Tone: warm, lighthearted, energetic.",
                "thirdPerson": False,
                "tags": ["fantasy", "city"],
            },
            "state": {
                "storySummary": "You arrived in the city at dawn.",
                "instructions": {"scenario": "Write vivid character-driven scenes."},
                "storyCards": [
                    {
                        "id": "card_tenzin",
                        "title": "Tenzin",
                        "type": "character",
                        "keys": "Tenzin,master",
                        "value": "Master airbender and calm mentor.",
                        "isPinned": False,
                        "useForCharacterCreation": True,
                    }
                ],
            },
        }

        st, res = self._req("POST", "/api/scenarios/import", {"data": raw})
        self.assertEqual(st, 201)
        sc = res["scenario"]
        self.assertEqual(sc["name"], raw["adventure"]["title"])
        self.assertEqual(sc["description"], raw["adventure"]["description"])
        self.assertEqual(sc["plot_essentials"], raw["adventure"]["memory"])
        self.assertEqual(sc["authors_note"], raw["adventure"]["authorsNote"])
        self.assertEqual(sc["third_person"], raw["adventure"]["thirdPerson"])
        self.assertEqual(sc["story_summary"], raw["state"]["storySummary"])
        self.assertEqual(sc["ai_instructions"], raw["state"]["instructions"]["scenario"])
        self.assertEqual(len(sc["story_cards"]), len(raw["state"]["storyCards"]))

        for orig, imp in zip(raw["state"]["storyCards"], sc["story_cards"]):
            self.assertEqual(imp["id"], orig["id"])
            self.assertEqual(imp["title"], orig["title"])
            self.assertEqual(imp["card_type"], orig["type"])
            self.assertEqual(imp["keys"], orig["keys"])
            self.assertEqual(imp["entry"], orig["value"])
            self.assertEqual(imp["is_pinned"], orig["isPinned"])
            self.assertEqual(imp["use_for_character_creation"], orig["useForCharacterCreation"])

        # Play imported scenario and verify Story Card triggering works
        st, play_res = self._req("POST", "/api/stories", {"scenario_id": sc["id"]})
        self.assertEqual(st, 201)
        story_id = play_res["story"]["id"]
        self._req("POST", f"/api/stories/{story_id}/append", {"mode": "say", "text": "Hi Tenzin!"})
        _, ctx = self._req("GET", f"/api/stories/{story_id}/context")
        self.assertIn("Tenzin", [c["title"] for c in ctx["triggered_cards"]])

    def test_required_dynamic_budget_and_memory_bank(self):
        # Verify trim_incomplete_sentence
        self.assertEqual(
            harness.trim_incomplete_sentence("The door shuts. Wind howls down the"),
            "The door shuts.",
        )
        self.assertEqual(
            harness.trim_incomplete_sentence("Single unfinished clause without punctuation"),
            "Single unfinished clause without punctuation",
        )

        story = harness.Story(
            id="budget-test",
            title="Budget Test",
            ai_instructions="Write crisply in second person present tense.",
            plot_essentials="You carry a bronze compass.",
            authors_note="Gothic mystery tone.",
            story_summary="Earlier, you escaped the sunken library " + ("with ancient maps " * 300),
            memories=[
                harness.MemoryItem(id="m1", text="Captain Veyra warned you about the lighthouse fog horn."),
                harness.MemoryItem(id="m2", text="A bakery in Oakhaven sells saffron rolls on Tuesdays."),
            ],
            settings=harness.StorySettings(
                context_length=1024,
                memory_bank_enabled=True,
                auto_summarize=True,
            ),
            segments=[
                harness.Segment(id="s0", kind="story", text="Old scene " + ("filler words " * 120)),
                harness.Segment(id="s1", kind="story", text="Another old scene " + ("filler words " * 120)),
                harness.Segment(id="s2", kind="do", text="You listen for the lighthouse fog horn."),
            ],
        )

        plan = harness.build_context_plan(story, apply_context_scripts=False, bump_memory_uses=True)
        self.assertEqual(plan["context_limit"], 1024)
        sec = {s["key"]: s["text"] for s in plan["sections"]}
        # Required elements: Front Memory / Last Action, Author's Note, Plot Essentials, AI Instructions preserved;
        # huge Story Summary should be truncated if it exceeds remaining Required budget (70% = ~716 tokens).
        self.assertIn("lighthouse fog horn", sec["history"])
        self.assertEqual(sec["authors_note"], "Gothic mystery tone.")
        self.assertEqual(sec["plot_essentials"], "You carry a bronze compass.")
        self.assertLess(len(sec["story_summary"]), len(story.story_summary))
        self.assertTrue(sec["story_summary"].startswith("Earlier, you escaped the sunken library"))
        # Old filler segments should be trimmed while keeping the last action
        self.assertNotIn("Old scene filler", sec["history"])
        # Memory Bank TF-IDF should prefer lighthouse memory m1 over bakery m2 and bump m1 uses
        used_ids = [m["id"] for m in plan["used_memories"]]
        self.assertIn("m1", used_ids)
        self.assertEqual(story.memories[0].uses, 1)

    def test_undo_redo_and_erase_to_here(self):
        st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        self.assertEqual(st, 201)
        story_id = created["story"]["id"]
        s0_id = created["story"]["segments"][0]["id"]

        _, a1 = self._req("POST", f"/api/stories/{story_id}/append", {"mode": "do", "text": "step one"})
        _, a2 = self._req("POST", f"/api/stories/{story_id}/append", {"mode": "do", "text": "step two"})
        _, a3 = self._req("POST", f"/api/stories/{story_id}/append", {"mode": "do", "text": "step three"})
        s1_id = a1["segment"]["id"]
        s2_id = a2["segment"]["id"]

        # Undo then Redo
        st, undo_res = self._req("POST", f"/api/stories/{story_id}/undo", {})
        self.assertEqual(st, 200)
        self.assertTrue(undo_res["undone"])
        self.assertEqual(len(undo_res["story"]["segments"]), 3)

        st, redo_res = self._req("POST", f"/api/stories/{story_id}/redo", {})
        self.assertEqual(st, 200)
        self.assertTrue(redo_res["redone"])
        self.assertEqual(len(redo_res["story"]["segments"]), 4)

        # Erase to Here via dedicated endpoint on s2 keeps opening + s1 (erases s2 + s3)
        st, eth_res = self._req("POST", f"/api/stories/{story_id}/erase-to-here", {"seg_id": s2_id})
        self.assertEqual(st, 200)
        self.assertEqual(eth_res["erased"], 2)
        self.assertEqual([s["id"] for s in eth_res["story"]["segments"]], [s0_id, s1_id])

        # Undo restores erased segments
        st, undo_eth = self._req("POST", f"/api/stories/{story_id}/undo", {})
        self.assertEqual(st, 200)
        self.assertTrue(undo_eth["undone"])
        self.assertEqual(len(undo_eth["story"]["segments"]), 4)

        # Inline /eth command via segment PATCH also erases from s1 onward
        st, patch_eth = self._req(
            "PATCH",
            f"/api/stories/{story_id}/segments/{s1_id}",
            {"text": "/eth"},
        )
        self.assertEqual(st, 200)
        self.assertTrue(patch_eth.get("erased_to_here"))
        self.assertEqual([s["id"] for s in patch_eth["story"]["segments"]], [s0_id])

    def test_cards_import_export_and_adventure_zip(self):
        import io
        import zipfile

        st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        self.assertEqual(st, 201)
        story_id = created["story"]["id"]

        # Import Story Cards JSON array with duplicate + invalid item
        import_payload = {
            "cards": [
                {
                    "keys": "elara, sage",
                    "value": "Elara guards the lantern archive.",
                    "type": "character",
                    "title": "Elara",
                    "description": "Keeper of lanterns",
                    "isPinned": True,
                    "useForCharacterCreation": False,
                },
                {
                    "keys": "elara, sage",
                    "value": "Elara guards the lantern archive.",
                    "type": "character",
                    "title": "Elara Dup",
                },
                {
                    "keys": "broken",
                    "value": "",
                },
            ]
        }
        st, imp_res = self._req("POST", f"/api/stories/{story_id}/cards/import", import_payload)
        self.assertEqual(st, 200)
        self.assertEqual(imp_res["stats"], {"imported": 1, "duplicates": 1, "skipped": 1})

        # Export Story Cards JSON array
        st, exp_cards = self._req("GET", f"/api/stories/{story_id}/cards/export")
        self.assertEqual(st, 200)
        self.assertEqual(len(exp_cards["cards"]), 1)
        self.assertEqual(exp_cards["cards"][0]["title"], "Elara")
        self.assertTrue(exp_cards["cards"][0]["isPinned"])

        # Update details & download Adventure .zip
        st, patched = self._req(
            "PATCH",
            f"/api/stories/{story_id}",
            {"title": "Lantern Archive", "description": "A rainy night.", "tags": ["mystery", "fantasy"]},
        )
        self.assertEqual(st, 200)
        self.assertEqual(patched["story"]["description"], "A rainy night.")

        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/stories/{story_id}/export", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            zip_bytes = resp.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = set(zf.namelist())
            self.assertTrue({"story.txt", "adventure.json", "story_cards.json"}.issubset(names))
            adv = json.loads(zf.read("adventure.json").decode("utf-8"))
            self.assertEqual(adv["title"], "Lantern Archive")
            self.assertEqual(adv["tags"], ["mystery", "fantasy"])

    def test_memory_maintenance_mock_llm(self):
        prompts_seen = []

        class MockMemoryLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                prompts_seen.append(body["messages"][-1]["content"])
                if "Compress RPG events" in body["messages"][-2]["content"]:
                    reply = "The traveler unlocked the iron grate. A brass owl warned of rising tides."
                else:
                    reply = "You unlocked the grate below the lighthouse as a brass owl warned of rising tides."
                payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockMemoryLLM)
        llm_thread = threading.Thread(target=llm.serve_forever, daemon=True)
        llm_thread.start()
        old_llm = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{llm.server_address[1]}"
        try:
            st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            self.assertEqual(st, 201)
            story_id = created["story"]["id"]
            # Toggle Memory Bank + Auto Summarization on and append 17 actions (18 total segs -> 2 Memory Bank chunks + Auto Summary)
            self._req(
                "PATCH",
                f"/api/stories/{story_id}",
                {"settings": {"memory_bank_enabled": True, "auto_summarize": True}},
            )
            for i in range(17):
                self._req("POST", f"/api/stories/{story_id}/append", {"mode": "do", "text": f"inspect rune {i}"})

            server._run_memory_maintenance(story_id)
            _, after = self._req("GET", f"/api/stories/{story_id}")
            story = after["story"]
            self.assertEqual(len(story["memories"]), 2)
            self.assertIn("brass owl", story["memories"][0]["text"])
            self.assertIn("brass owl", story["story_summary"])
            self.assertEqual(len(prompts_seen), 3)
        finally:
            server.LLM_URL = old_llm
            llm.shutdown()
            llm.server_close()

    def test_import_url_and_character_creator_parity(self):
        # 1. Validation error when URL is empty
        with self.assertRaises(urllib.request.HTTPError) as cm:
            self._req("POST", "/api/scenarios/import-url", {"url": ""})
        self.assertEqual(cm.exception.code, 400)
        cm.exception.close()

        # 2. Mock Playwright URL fetch returning AI Dungeon characterCreator payload
        mock_payload = {
            "details": {
                "title": "Faerun Sample",
                "description": "High fantasy sandbox.",
                "type": "characterCreator",
                "thirdPerson": False,
            },
            "scenario": {
                "id": "sc123",
                "shortId": "demoCC12",
                "type": "characterCreator",
                "state": {
                    "prompt": "A land of wizards for ${character.name} (${character.gender}).",
                    "plotEssentials": "Keep magic wondrous.",
                    "authorsNote": "Epic fantasy tone.",
                    "instructions": {"scenario": "Follow character choices faithfully."},
                    "storySummary": "",
                },
                "inheritedStoryCards": [
                    {
                        "id": "c_inh",
                        "type": "location",
                        "keys": "Waterdeep",
                        "value": "A bustling port metropolis.",
                        "title": "Waterdeep",
                        "description": "City of Splendors",
                        "useForCharacterCreation": True,
                    }
                ],
                "storyCards": [
                    {
                        "id": "c_race",
                        "type": "race",
                        "keys": "Elf",
                        "value": "Graceful long-lived folk of the forests.",
                        "title": "Elf",
                        "description": "Forest-born elf",
                        "useForCharacterCreation": True,
                    },
                    {
                        "id": "c_del",
                        "type": "race",
                        "keys": "Deleted",
                        "value": "Should be ignored",
                        "title": "Deleted",
                        "deletedAt": "2026-01-01T00:00:00Z",
                        "useForCharacterCreation": True,
                    },
                ],
            },
        }
        orig_fetch = server.fetch_aidungeon_url_payload
        server.fetch_aidungeon_url_payload = lambda url: mock_payload
        try:
            st, imp = self._req(
                "POST",
                "/api/scenarios/import-url",
                {"url": "https://play.aidungeon.com/scenario/demoCC12/faerun-sample"},
            )
            self.assertEqual(st, 201)
            sc = imp["scenario"]
            self.assertEqual(sc["scenario_type"], "character_creator")
            self.assertEqual(sc["name"], "Faerun Sample")
            self.assertEqual(len(sc["story_cards"]), 2)  # deletedAt filtered out
            self.assertEqual(sc["story_cards"][0]["description"], "City of Splendors")

            # Custom character creation preserves premise + selected cards + pins chosen cards
            st, custom_story_res = self._req(
                "POST",
                "/api/stories",
                {
                    "scenario_id": sc["id"],
                    "placeholder_answers": {"character.name": "Lyra", "character.gender": "Female"},
                    "selected_card_ids": ["c_race"],
                },
            )
            self.assertEqual(st, 201)
            cs = custom_story_res["story"]
            self.assertEqual(cs["segments"], [])
            self.assertIn("wizards for Lyra (Female)", cs["world_description"])
            self.assertIn("CHARACTER INFORMATION", cs["plot_essentials"])
            self.assertIn("Name: Lyra", cs["plot_essentials"])
            self.assertIn("Gender: Female", cs["plot_essentials"])
            self.assertIn("Race: Elf", cs["plot_essentials"])
            self.assertIn("You are Lyra, [Female, Elf]", cs["plot_essentials"])
            pinned_ids = [c["id"] for c in cs["story_cards"] if c["is_pinned"]]
            self.assertEqual(pinned_ids, ["c_race"])

            # Empty segments on Character Creator builds an opening generation prompt
            plan = harness.build_context_plan(harness.load_story(cs["id"]))
            self.assertIn("opening scene", plan["messages"][-1]["content"].lower())
            self.assertIn("World Description", plan["messages"][0]["content"])

            # Quickstart selects random name, gender, and one card per category
            st, qs_res = self._req(
                "POST",
                "/api/stories",
                {"scenario_id": sc["id"], "quickstart": True},
            )
            self.assertEqual(st, 201)
            qs = qs_res["story"]
            self.assertEqual(len([c for c in qs["story_cards"] if c["is_pinned"]]), 2)
            self.assertIn("CHARACTER INFORMATION", qs["plot_essentials"])
        finally:
            server.fetch_aidungeon_url_payload = orig_fetch

        # 3. Multiple-choice scenario options imported as multiple_choice
        mc_sc = harness.import_aidungeon_json(
            {
                "details": {"title": "Crossroads", "type": "multiple_choice"},
                "scenario": {
                    "options": [
                        {"shortId": "opt1", "title": "Rogue Path", "prompt": "Shadows cling to your cloak."},
                        {"shortId": "opt2", "title": "Mage Path", "prompt": "Arcane sparks dance at your fingertips."},
                    ]
                },
            }
        )
        self.assertEqual(mc_sc.scenario_type, "multiple_choice")
        self.assertEqual(len(mc_sc.choices), 2)
        self.assertEqual(mc_sc.choices[0]["label"], "Rogue Path")
        self.assertEqual(mc_sc.choices[1]["opening"], "Arcane sparks dance at your fingertips.")

    def test_guide_mode_and_retry_with_changes_sse(self):
        seen_payloads = []

        class MockGuideLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                seen_payloads.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                reply = "A raven drops a silver key." if len(seen_payloads) == 1 else "A golden owl drops a brass key."
                chunks = [
                    {"choices": [{"delta": {"content": reply}}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                ]
                for c in chunks:
                    self.wfile.write(f"data: {json.dumps(c)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockGuideLLM)
        t = threading.Thread(target=llm.serve_forever, daemon=True)
        t.start()
        old_llm = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{llm.server_address[1]}"
        try:
            st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            self.assertEqual(st, 201)
            story_id = created["story"]["id"]
            init_count = len(created["story"]["segments"])

            # Guide mode triggers AI response with guidance without adding a visible user prose segment
            req1 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"mode": "guide", "text": "Introduce a mysterious raven"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req1, timeout=5) as resp:
                resp.read()

            _, after_guide = self._req("GET", f"/api/stories/{story_id}")
            s1 = after_guide["story"]
            self.assertEqual(len(s1["segments"]), init_count + 1)
            self.assertEqual(s1["segments"][-1]["kind"], "ai")
            self.assertIn("Player Guidance", seen_payloads[0]["messages"][-1]["content"])
            self.assertEqual(s1["last_generation_context"]["guide_text"], "Introduce a mysterious raven")

            # Retry with changes pops old AI segment and passes revision note + previous draft
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"retry": True, "retry_instructions": "Make it a golden owl instead"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                resp.read()

            _, after_retry = self._req("GET", f"/api/stories/{story_id}")
            s2 = after_retry["story"]
            self.assertEqual(len(s2["segments"]), init_count + 1)
            self.assertIn("golden owl", s2["segments"][-1]["text"])
            last_msg = seen_payloads[1]["messages"][-1]["content"]
            self.assertIn("Make it a golden owl instead", last_msg)
            self.assertIn("A raven drops a silver key.", last_msg)

            # Retry Stack stores both variants and cycles cleanly
            self.assertEqual(len(s2["segments"][-1]["variants"]), 2)
            self.assertEqual(s2["segments"][-1]["variant_idx"], 1)
            st, cyc = self._req("POST", f"/api/stories/{story_id}/retry-cycle", {"direction": -1})
            self.assertEqual(st, 200)
            self.assertTrue(cyc["changed"])
            self.assertEqual(cyc["story"]["segments"][-1]["text"], "A raven drops a silver key.")
            self.assertEqual(cyc["story"]["segments"][-1]["variant_idx"], 0)

            # Erase pops last action and is undoable
            st, er = self._req("POST", f"/api/stories/{story_id}/erase", {})
            self.assertEqual(st, 200)
            self.assertTrue(er["erased"])
            self.assertEqual(len(er["story"]["segments"]), init_count)
            st, un = self._req("POST", f"/api/stories/{story_id}/undo", {})
            self.assertEqual(st, 200)
            self.assertTrue(un["undone"])
            self.assertEqual(len(un["story"]["segments"]), init_count + 1)

            # GET /api/scripts works cleanly (no NameError regression)
            st, scripts_list = self._req("GET", "/api/scripts")
            self.assertEqual(st, 200)
            self.assertIsInstance(scripts_list["scripts"], list)

            # Presence/frequency penalty forwarding
            self._req(
                "PATCH",
                f"/api/stories/{story_id}",
                {"settings": {"presence_penalty": 0.4, "frequency_penalty": 0.25}},
            )
            req3 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req3, timeout=5) as resp:
                resp.read()
            self.assertAlmostEqual(seen_payloads[-1]["presence_penalty"], 0.4)
            self.assertAlmostEqual(seen_payloads[-1]["frequency_penalty"], 0.25)
        finally:
            server.LLM_URL = old_llm
            llm.shutdown()
            llm.server_close()

    def test_generate_story_card_entry_mock_llm(self):
        class MockCardLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                payload = json.dumps({
                    "choices": [{"message": {"content": "Captain Veyra commands the Silver Gale."}}]
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockCardLLM)
        t = threading.Thread(target=llm.serve_forever, daemon=True)
        t.start()
        old_llm = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{llm.server_address[1]}"
        try:
            st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            self.assertEqual(st, 201)
            story_id = created["story"]["id"]
            st, res = self._req(
                "POST",
                f"/api/stories/{story_id}/cards/generate",
                {"title": "Captain Veyra", "card_type": "Character", "wrap": "[]"},
            )
            self.assertEqual(st, 200)
            self.assertEqual(res["entry"], "[Captain Veyra commands the Silver Gale.]")
        finally:
            server.LLM_URL = old_llm
            llm.shutdown()
            llm.server_close()

    def test_nested_multiple_choice_inheritance_and_dedup(self):
        # Root -> Branch (era, cards, plot_essentials) -> Leaf (mage class, inherits cards, overrides opening)
        st, created_sc = self._req(
            "POST",
            "/api/scenarios",
            {
                "name": "Grand Chronicles",
                "scenario_type": "multiple_choice",
                "plot_essentials": "World rule: Mana shapes all.",
                "ai_instructions": "Root instructions.",
                "choices": [
                    {
                        "id": "era_ash",
                        "label": "Ashen Age",
                        "plot_essentials": "Era: The sky is always ember-lit.",
                        "authors_note": "Gritty dark fantasy.",
                        "story_cards": [
                            {"id": "c_ash", "title": "Ash Ward", "card_type": "Location", "keys": "ash", "entry": "Cursed citadel."}
                        ],
                        "choices": [
                            {
                                "id": "cls_mage",
                                "label": "Pyromancer",
                                "opening": "You kindle a flame as ${character.name} in ${city}.",
                                "plot_essentials": "World rule: Mana shapes all.",
                                "choices": [
                                    {
                                        "id": "origin_noble",
                                        "label": "Exiled Noble Pyromancer",
                                        "description": "Start as an exiled court mage.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )
        self.assertEqual(st, 201)
        sc = created_sc["scenario"]
        sc_id = sc["id"]

        # Create story selecting leaf via choice_path
        st, story_res = self._req(
            "POST",
            "/api/stories",
            {
                "scenario_id": sc_id,
                "choice_path": ["era_ash", "cls_mage", "origin_noble"],
                "placeholder_answers": {"character.name": "Ignis", "city": "Valen"},
            },
        )
        self.assertEqual(st, 201)
        story = story_res["story"]
        # Leaf label inherited as story title, opening inherited from parent cls_mage
        self.assertEqual(story["title"], "Exiled Noble Pyromancer")
        self.assertEqual(story["segments"][0]["text"], "You kindle a flame as Ignis in Valen.")
        # Inherited branch story cards + authors_note + deduplicated plot_essentials
        self.assertEqual(story["authors_note"], "Gritty dark fantasy.")
        self.assertEqual(story["ai_instructions"], "Root instructions.")
        self.assertEqual(len(story["story_cards"]), 1)
        self.assertEqual(story["story_cards"][0]["title"], "Ash Ward")
        self.assertEqual(story["plot_essentials"].count("World rule: Mana shapes all."), 1)
        self.assertIn("Era: The sky is always ember-lit.", story["plot_essentials"])

        # Direct leaf lookup by choice_id alone works too
        st, by_leaf = self._req(
            "POST",
            "/api/stories",
            {
                "scenario_id": sc_id,
                "choice_id": "origin_noble",
                "placeholder_answers": {"character.name": "Lyra", "city": "Sol"},
            },
        )
        self.assertEqual(st, 201)
        self.assertEqual(by_leaf["story"]["title"], "Exiled Noble Pyromancer")
        self.assertEqual(by_leaf["story"]["segments"][0]["text"], "You kindle a flame as Lyra in Sol.")

    def test_action_markers_warnings_and_remove_repeated_sentences(self):
        # 1. Verify remove_repeated_leading_sentences strips duplicated opening sentences
        cleaned, removed = harness.remove_repeated_leading_sentences(
            "You step into the tavern. A bard tunes her lute by the fire.",
            ["The rain pours outside. You step into the tavern."],
        )
        self.assertEqual(cleaned, "A bard tunes her lute by the fire.")
        self.assertEqual(removed, ["You step into the tavern."])

        # 2. Verify Do/Say get `>` prefix and tight context produces warnings + reserved_response_tokens
        st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        self.assertEqual(st, 201)
        story_id = created["story"]["id"]
        self._req("POST", f"/api/stories/{story_id}/append", {"mode": "do", "text": "inspect the bar"})
        self._req("POST", f"/api/stories/{story_id}/append", {"mode": "say", "text": "Any news tonight?"})

        story = harness.load_story(story_id)
        plan = harness.build_context_plan(story)
        history_sec = next(s for s in plan["sections"] if s["key"] == "history")
        self.assertIn("> You inspect the bar.", history_sec["text"])
        self.assertIn('> You say, "Any news tonight?"', history_sec["text"])
        self.assertIn("> You inspect the bar.", plan["messages"][-1]["content"])
        self.assertGreater(plan["reserved_response_tokens"], 0)

        # Trigger context warning by shrinking context_length below total needed tokens with extra cards
        story.settings.context_length = 260
        story.settings.max_tokens = 120
        for i in range(6):
            story.story_cards.append(
                harness.StoryCard(
                    id=f"sc_w_{i}",
                    title=f"Lore {i}",
                    keys="bar",
                    entry=" ".join([f"detail{i}"] * 60),
                    is_pinned=True,
                )
            )
        harness.save_story(story)
        st, report = self._req("GET", f"/api/stories/{story_id}/context")
        self.assertEqual(st, 200)
        self.assertTrue(len(report.get("warnings") or []) > 0)
        self.assertGreater(report.get("reserved_response_tokens", 0), 0)

        # 3. Verify SSE generation records removed_context when model repeats previous sentence
        seen = []

        class MockRepeatLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                reply = '> You say, "Any news tonight?" The barkeep leans closer.'
                chunk = {"choices": [{"delta": {"content": reply}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.write(b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockRepeatLLM)
        t = threading.Thread(target=llm.serve_forever, daemon=True)
        t.start()
        old_llm = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{llm.server_address[1]}"
        try:
            story.settings.context_length = 98304
            harness.save_story(story)
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
            _, after = self._req("GET", f"/api/stories/{story_id}")
            lgc = after["story"]["last_generation_context"]
            self.assertEqual(after["story"]["segments"][-1]["text"], "The barkeep leans closer.")
            self.assertIn('> You say, "Any news tonight?"', lgc["removed_context"])
            self.assertIn("warnings", lgc)
            self.assertIn("reserved_response_tokens", lgc)
        finally:
            server.LLM_URL = old_llm
            llm.shutdown()
            llm.server_close()

    def test_global_ai_settings_persistence(self):
        # Default settings can be inspected and updated globally
        st, got = self._req("GET", "/api/settings")
        self.assertEqual(st, 200)
        self.assertAlmostEqual(got["settings"]["temperature"], 0.85)

        st, patched = self._req(
            "PATCH",
            "/api/settings",
            {"settings": {"temperature": 0.0, "max_tokens": 512, "memory_bank_enabled": True}},
        )
        self.assertEqual(st, 200)
        self.assertAlmostEqual(patched["settings"]["temperature"], 0.0)
        self.assertEqual(patched["settings"]["max_tokens"], 512)
        self.assertTrue(patched["settings"]["memory_bank_enabled"])

        # Newly created stories inherit persisted global AI settings
        st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        self.assertEqual(st, 201)
        story = created["story"]
        self.assertAlmostEqual(story["settings"]["temperature"], 0.0)
        self.assertEqual(story["settings"]["max_tokens"], 512)
        self.assertTrue(story["settings"]["memory_bank_enabled"])

        # PATCH /api/stories/<id> with save_as_default updates future stories too
        st, upd = self._req(
            "PATCH",
            f"/api/stories/{story['id']}",
            {"settings": {"temperature": 0.65, "context_length": 16384}, "save_as_default": True},
        )
        self.assertEqual(st, 200)
        st, created2 = self._req("POST", "/api/stories", {"scenario_id": "station"})
        self.assertEqual(st, 201)
        self.assertAlmostEqual(created2["story"]["settings"]["temperature"], 0.65)
        self.assertEqual(created2["story"]["settings"]["context_length"], 16384)

    def test_endpoint_switching_and_auth_header(self):
        seen_auth = []
        seen_paths = []
        seen_payloads = []

        class MockCloudLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                seen_auth.append(self.headers.get("Authorization"))
                seen_paths.append(self.path)
                if self.path == "/v1/models":
                    payload = json.dumps({"data": [{"id": "solo-model-v1"}]}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                seen_auth.append(self.headers.get("Authorization"))
                seen_paths.append(self.path)
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                seen_payloads.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunk = {"choices": [{"delta": {"content": "The cloud model replies."}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.write(b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockCloudLLM)
        t = threading.Thread(target=llm.serve_forever, daemon=True)
        t.start()
        try:
            base_v1 = f"http://127.0.0.1:{llm.server_address[1]}/v1"

            # Verify /api/llm/models queries /v1/models cleanly without double /v1/v1
            st, mres = self._req(
                "POST",
                "/api/llm/models",
                {"llm_url": base_v1, "api_key": "sk-test-secret-9999"},
            )
            self.assertEqual(st, 200)
            self.assertEqual(mres["models"], ["solo-model-v1"])
            self.assertIn("/v1/models", seen_paths)
            self.assertIn("Bearer sk-test-secret-9999", seen_auth)

            # Persist endpoint config with masked API key on GET
            st, cres = self._req(
                "POST",
                "/api/llm/config",
                {"llm_url": base_v1, "api_key": "sk-test-secret-9999", "model": ""},
            )
            self.assertEqual(st, 200)
            self.assertTrue(cres["config"]["has_api_key"])
            self.assertNotIn("sk-test-secret-9999", json.dumps(cres))
            self.assertEqual(cres["status"]["state"], "ready")
            self.assertEqual(cres["status"]["model"], "solo-model-v1")

            st, gcfg = self._req("GET", "/api/llm/config")
            self.assertEqual(st, 200)
            self.assertEqual(gcfg["config"]["llm_url"], base_v1)
            self.assertTrue(gcfg["config"]["has_api_key"])

            # Verify generation uses configured URL, Bearer token, and discovered model
            st, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            self.assertEqual(st, 201)
            story_id = created["story"]["id"]
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
            self.assertIn("/v1/chat/completions", seen_paths)
            self.assertEqual(seen_payloads[-1]["model"], "solo-model-v1")
            self.assertEqual(seen_auth[-1], "Bearer sk-test-secret-9999")
            # /v1 OpenAI-compat URL should not send llama-cpp-only top_k / chat_template_kwargs
            self.assertNotIn("top_k", seen_payloads[-1])
            self.assertNotIn("chat_template_kwargs", seen_payloads[-1])
        finally:
            llm.shutdown()
            llm.server_close()

    def test_inline_continue_anchor_overlap_and_merge(self):
        # 1. Suffix-prefix word overlap & echoed trailing quote stripping
        prev_block = 'Rain hits the glass. Elena leans close and whispers, "Do not trust the captain tonight."'
        cleaned_word, removed_word = harness.remove_repeated_leading_sentences(
            'Do not trust the captain tonight. She slips a brass key into your palm.',
            [prev_block],
        )
        self.assertEqual(cleaned_word, "She slips a brass key into your palm.")
        self.assertTrue(len(removed_word) >= 1)

        cleaned_quote, removed_quote = harness.remove_repeated_leading_sentences(
            'She whispers, "Do not trust the captain tonight." Footsteps echo outside.',
            [prev_block],
        )
        self.assertEqual(cleaned_quote, "Footsteps echo outside.")
        self.assertTrue(len(removed_quote) >= 1)

        # Incomplete ellipsis / unclosed quote overlap & inline join (e.g. `"You are...` -> `"You are... quite incorrigible,"`)
        ellipsis_prev = 'She puffs her cheeks out.\n\n"You are...'
        ellipsis_cont = '"You are... quite incorrigible," she repeats, her voice low.'
        cleaned_ellipsis, removed_ellipsis = harness.remove_repeated_leading_sentences(
            ellipsis_cont,
            [ellipsis_prev],
        )
        self.assertEqual(cleaned_ellipsis, 'quite incorrigible," she repeats, her voice low.')
        self.assertTrue(len(removed_ellipsis) >= 1)
        self.assertEqual(
            harness.join_ai_continuation(ellipsis_prev, cleaned_ellipsis),
            'She puffs her cheeks out.\n\n"You are... quite incorrigible," she repeats, her voice low.',
        )

        # 2. join_ai_continuation handles mid-sentence vs paragraph break cleanly
        self.assertEqual(
            harness.join_ai_continuation("Elena reaches for", "the iron latch."),
            "Elena reaches for the iron latch.",
        )
        self.assertEqual(
            harness.join_ai_continuation('She glances back. "Ready?"', "You nod once."),
            'She glances back. "Ready?"\n\nYou nod once.',
        )

        # 3. Context placement: Author's Note sits before the latest turn/continuation anchor
        story = harness.Story(
            id="cont1",
            title="Continue Anchor",
            authors_note="Keep dialogue taut.",
            segments=[
                harness.Segment(id="1", kind="opening", text="The harbor fog thickens."),
                harness.Segment(id="2", kind="ai", text='Elena whispers, "Check the crate."'),
            ],
        )
        msgs = harness.build_chat_messages(story)
        last_user = msgs[-1]["content"]
        self.assertLess(last_user.index("Keep dialogue taut."), last_user.index('Elena whispers, "Check the crate."'))

        # 4. SSE Continue after AI merges inline into the existing AI segment and supports Undo
        turn_count = {"n": 0}

        class MockContinueLLM(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(length)
                turn_count["n"] += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if turn_count["n"] == 1:
                    reply = 'The innkeeper slides a mug across the oak bar and mutters, "Stay off the docks after midnight."'
                else:
                    reply = 'He mutters, "Stay off the docks after midnight." A gust slams the shutters open.'
                chunk = {"choices": [{"delta": {"content": reply}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.write(b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        llm = ThreadingHTTPServer(("127.0.0.1", 0), MockContinueLLM)
        t = threading.Thread(target=llm.serve_forever, daemon=True)
        t.start()
        orig_llm_url = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{llm.server_address[1]}"
        try:
            _, created = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
            story_id = created["story"]["id"]
            init_count = len(created["story"]["segments"])

            # First turn
            req1 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"mode": "do", "text": "sit at the bar"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req1, timeout=5) as resp:
                resp.read()

            _, s_after_1 = self._req("GET", f"/api/stories/{story_id}")
            self.assertEqual(len(s_after_1["story"]["segments"]), init_count + 2)
            first_ai_id = s_after_1["story"]["segments"][-1]["id"]

            # Continue adds a separate undoable/erasable AI segment with echoed dialogue stripped
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                resp.read()

            _, s_after_2 = self._req("GET", f"/api/stories/{story_id}")
            self.assertEqual(len(s_after_2["story"]["segments"]), init_count + 3)
            self.assertEqual(s_after_2["story"]["segments"][-2]["id"], first_ai_id)
            self.assertEqual(
                s_after_2["story"]["segments"][-2]["text"],
                'The innkeeper slides a mug across the oak bar and mutters, "Stay off the docks after midnight."',
            )
            self.assertEqual(
                s_after_2["story"]["segments"][-1]["text"],
                "A gust slams the shutters open.",
            )

            # Erase removes ONLY the continuation segment, keeping the earlier AI segment intact
            st, er_res = self._req("POST", f"/api/stories/{story_id}/erase", {})
            self.assertEqual(st, 200)
            self.assertTrue(er_res["erased"])
            self.assertEqual(len(er_res["story"]["segments"]), init_count + 2)
            self.assertEqual(er_res["story"]["segments"][-1]["id"], first_ai_id)
            self.assertEqual(
                er_res["story"]["segments"][-1]["text"],
                'The innkeeper slides a mug across the oak bar and mutters, "Stay off the docks after midnight."',
            )

            # Undo restores the erased continuation segment
            st, undo_res = self._req("POST", f"/api/stories/{story_id}/undo", {})
            self.assertEqual(st, 200)
            self.assertTrue(undo_res["undone"])
            self.assertEqual(len(undo_res["story"]["segments"]), init_count + 3)
            self.assertEqual(
                undo_res["story"]["segments"][-1]["text"],
                "A gust slams the shutters open.",
            )
        finally:
            server.LLM_URL = orig_llm_url
            llm.shutdown()
            llm.server_close()

    def test_aidungeon_script_compat_autocards_innerself(self):
        # Simulate LewdLeah Auto-Cards / Inner-Self idioms:
        # 1) Calling library helper before modifier(text), reading global `stop`, returning [text, stop]
        # 2) Reading/mutating storyCards[i].value, .description, addStoryCard(..., description), updateStoryCard(..., description)
        # 3) Accessing state.memory without pre-initialization and reading info.maxChars / history[].type
        lib_code = """
        function AutoCompat(hook, t, s) {
          if (hook === 'input') {
            state.seenInfo = {
              hasMaxChars: typeof info.maxChars === 'number' && info.maxChars > 0,
              hasMemLen: typeof info.memoryLength === 'number',
              histStartType: history.length > 0 ? history[0].type : null,
            };
            // Verify state.memory exists by default without crashing
            const prevMem = state.memory.context || '';
            state.memory.context = prevMem ? prevMem : 'Active camp';
            // Create card with description (5th arg) and mutate via .value
            if (!storyCards.some((c) => c.title === 'Nera')) {
              const idx = addStoryCard('nera', 'Old bio', 'Character', 'Nera', 'Config notes v1');
              storyCards[idx].value = 'Updated Nera bio via .value';
              updateStoryCard(idx, 'nera,mage', storyCards[idx].value, 'Character', 'Nera', 'Config notes v2');
            }
            return t;
          }
          if (hook === 'context') {
            const lastSeg = history.length > 0 ? history[history.length - 1].text : '';
            if (lastSeg.includes('HALT_CONTEXT')) {
              state.message = 'Paused by context script';
              return [t, true];
            }
            if (lastSeg.includes('HIJACK_CARD')) {
              return ['<CARD_GEN_PROMPT>Create a card for Aldric</CARD_GEN_PROMPT>', false];
            }
            return [t + '\\n[InnerThoughts: watchful]', s];
          }
          if (hook === 'output') {
            if (t.includes('CARD_JSON:')) {
              addStoryCard({ keys: 'aldric', value: 'Aldric is a stern blacksmith.', type: 'Character', title: 'Aldric', description: 'Auto-generated' });
              state.message = 'Auto-Cards created Aldric!';
              return '';
            }
            return t;
          }
          return t;
        }
        """
        input_code = """
        const modifier = (text) => {
          text = AutoCompat('input', text);
          return { text };
        };
        modifier(text);
        """
        context_code = """
        const modifier = (text) => {
          [text, stop] = AutoCompat('context', text, stop);
          return { text, stop };
        };
        modifier(text);
        """
        output_code = """
        const modifier = (text) => {
          text = AutoCompat('output', text);
          return { text };
        };
        modifier(text);
        """

        _, story_res = self._req("POST", "/api/stories", {"scenario_id": "tavern"})
        story_id = story_res["story"]["id"]
        self._req(
            "PATCH",
            f"/api/stories/{story_id}",
            {
                "builtin_script": {
                    "enabled": True,
                    "library": lib_code,
                    "input": input_code,
                    "context": context_code,
                    "output": output_code,
                }
            },
        )

        # Verify context script stop: true prevents LLM call cleanly while persisting user segment
        captured_bodies = []

        class CompatLLMHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                captured_bodies.append(json.loads(raw))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                last_msg = captured_bodies[-1]["messages"][-1]["content"]
                reply = (
                    "CARD_JSON: Aldric the blacksmith"
                    if "<CARD_GEN_PROMPT>" in last_msg
                    else "She nods slowly."
                )
                self.wfile.write(
                    f"data: {json.dumps({'choices': [{'delta': {'content': reply}, 'finish_reason': 'stop'}]})}\n\n".encode("utf-8")
                )
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        mock_llm = ThreadingHTTPServer(("127.0.0.1", 0), CompatLLMHandler)
        mock_thread = threading.Thread(target=mock_llm.serve_forever, daemon=True)
        mock_thread.start()
        orig_llm_url = server.LLM_URL
        server.LLM_URL = f"http://127.0.0.1:{mock_llm.server_address[1]}"
        try:
            # Turn 1: HALT_CONTEXT -> context returns stop: true -> no LLM request fired
            req1 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"mode": "story", "text": "HALT_CONTEXT check"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req1, timeout=5) as resp:
                sse1 = resp.read().decode("utf-8")
            self.assertIn("Paused by context script", sse1)
            self.assertEqual(len(captured_bodies), 0)

            _, st1 = self._req("GET", f"/api/stories/{story_id}")
            s1 = st1["story"]
            self.assertTrue(s1["script_state"]["seenInfo"]["hasMaxChars"])
            self.assertTrue(s1["script_state"]["seenInfo"]["hasMemLen"])
            self.assertEqual(s1["script_state"]["seenInfo"]["histStartType"], "start")
            self.assertEqual(s1["story_cards"][0]["entry"], "Updated Nera bio via .value")
            self.assertEqual(s1["story_cards"][0]["description"], "Config notes v2")

            # Turn 2: HIJACK_CARD -> wholesale prompt replacement omits RPG system prompt,
            # output script turns response into Aldric Story Card and suppresses AI segment
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/stories/{story_id}/generate",
                data=json.dumps({"mode": "story", "text": "HIJACK_CARD trigger"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                resp.read()
            self.assertEqual(len(captured_bodies), 1)
            self.assertEqual(len(captured_bodies[0]["messages"]), 1)
            self.assertEqual(
                captured_bodies[0]["messages"][0]["content"],
                "<CARD_GEN_PROMPT>Create a card for Aldric</CARD_GEN_PROMPT>",
            )

            _, st2 = self._req("GET", f"/api/stories/{story_id}")
            s2 = st2["story"]
            self.assertEqual(s2["script_state"]["message"], "Auto-Cards created Aldric!")
            self.assertEqual(len(s2["story_cards"]), 2)
            self.assertEqual(s2["story_cards"][1]["entry"], "Aldric is a stern blacksmith.")
            self.assertEqual(s2["story_cards"][1]["description"], "Auto-generated")
            self.assertEqual(s2["segments"][-1]["text"], "HIJACK_CARD trigger")
        finally:
            server.LLM_URL = orig_llm_url
            mock_llm.shutdown()
            mock_llm.server_close()

    def test_multiple_choice_community_scripts_option(self):
        orig_fetch = harness._fetch_community_source
        fetch_calls = []

        def fake_fetch(raw_base, filename, timeout=20):
            fetch_calls.append((raw_base, filename))
            if "Inner-Self" in raw_base:
                if filename == "library.js":
                    return "const MainSettings = { InnerSelf: { IS_AC_ENABLED_BY_DEFAULT: false } }; function InnerSelf() {}"
                if filename == "context.js":
                    return "InnerSelf('context'); const modifier = (text) => ({ text, stop }); modifier(text);"
                return "const modifier = (text) => ({ text }); modifier(text);"
            if filename == "library.js":
                return "function AutoCards(h, t) { return h === 'context' ? [t, false] : t; }"
            if filename == "context.js":
                return "const modifier = (text) => { [text, stop] = AutoCards('context', text, stop); return { text, stop }; }; modifier(text);"
            return "const modifier = (text) => ({ text }); modifier(text);"

        harness._fetch_community_source = fake_fetch
        try:
            # 1. Create a Multiple Choice scenario
            st, sc_res = self._req(
                "POST",
                "/api/scenarios",
                {
                    "name": "Guild Paths",
                    "scenario_type": "multiple_choice",
                    "choices": [
                        {"id": "c_mage", "label": "Mage", "opening": "You enter the arcane tower."},
                        {"id": "c_rogue", "label": "Rogue", "opening": "You slip into the alley."},
                    ],
                },
            )
            self.assertEqual(st, 201)
            sc_id = sc_res["scenario"]["id"]

            # 2. Start adventure with Auto-Cards only
            st, s_ac = self._req(
                "POST",
                "/api/stories",
                {"scenario_id": sc_id, "choice_id": "c_rogue", "enable_auto_cards": True},
            )
            self.assertEqual(st, 201)
            self.assertEqual(s_ac["story"]["attached_scripts"], [{"script_id": "community-auto-cards", "enabled": True}])

            # 3. Start adventure with BOTH Inner Self + Auto-Cards -> uses coordinated community-inner-self-ac
            st, s_both = self._req(
                "POST",
                "/api/stories",
                {
                    "scenario_id": sc_id,
                    "choice_id": "c_mage",
                    "enable_inner_self": True,
                    "enable_auto_cards": True,
                },
            )
            self.assertEqual(st, 201)
            self.assertEqual(
                s_both["story"]["attached_scripts"],
                [{"script_id": "community-inner-self-ac", "enabled": True}],
            )
            st, combo_res = self._req("GET", "/api/scripts/community-inner-self-ac")
            self.assertEqual(st, 200)
            self.assertIn("IS_AC_ENABLED_BY_DEFAULT: true", combo_res["script"]["library"])

            # 4. Cached scripts require zero additional fetches on subsequent calls
            count_before = len(fetch_calls)
            st, inst_res = self._req("POST", "/api/scripts/install-community", {"kind": "inner_self"})
            self.assertEqual(st, 200)
            self.assertEqual(inst_res["script"]["id"], "community-inner-self")
            self.assertEqual(len(fetch_calls), count_before)
        finally:
            harness._fetch_community_source = orig_fetch


if __name__ == "__main__":
    unittest.main()
