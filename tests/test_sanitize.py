"""Tests for the HTML sanitizer used by character "sections"."""

from app.services.sanitize import sanitize_html, sanitize_sections


# ---------------------------------------------------------------------------
# sanitize_html — allowlist behavior
# ---------------------------------------------------------------------------


class TestAllowedTags:
    def test_paragraph_preserved(self):
        assert sanitize_html("<p>hello</p>") == "<p>hello</p>"

    def test_bold_italic_preserved(self):
        assert sanitize_html("<b>x</b>") == "<b>x</b>"
        assert sanitize_html("<strong>x</strong>") == "<strong>x</strong>"
        assert sanitize_html("<i>x</i>") == "<i>x</i>"
        assert sanitize_html("<em>x</em>") == "<em>x</em>"

    def test_headings_preserved(self):
        for level in (1, 2, 3, 4, 5, 6):
            tag = f"h{level}"
            assert sanitize_html(f"<{tag}>x</{tag}>") == f"<{tag}>x</{tag}>"

    def test_lists_preserved(self):
        out = sanitize_html("<ul><li>a</li><li>b</li></ul>")
        assert out == "<ul><li>a</li><li>b</li></ul>"
        out = sanitize_html("<ol><li>1</li></ol>")
        assert out == "<ol><li>1</li></ol>"

    def test_blockquote_preserved(self):
        assert sanitize_html("<blockquote>q</blockquote>") == "<blockquote>q</blockquote>"

    def test_code_and_pre_preserved(self):
        assert sanitize_html("<code>x</code>") == "<code>x</code>"
        assert sanitize_html("<pre>raw</pre>") == "<pre>raw</pre>"

    def test_table_preserved(self):
        out = sanitize_html("<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>c</td></tr></tbody></table>")
        assert "<table>" in out and "<th>" in out and "<td>" in out

    def test_link_preserved(self):
        out = sanitize_html('<a href="https://example.com">x</a>')
        assert 'href="https://example.com"' in out

    def test_link_with_target_blank(self):
        out = sanitize_html('<a href="https://example.com" target="_blank">x</a>')
        assert 'target="_blank"' in out

    def test_link_with_title(self):
        out = sanitize_html('<a href="https://example.com" title="Hover">x</a>')
        assert 'title="Hover"' in out

    def test_image_preserved(self):
        out = sanitize_html('<img src="https://example.com/a.png" alt="logo">')
        assert 'src="https://example.com/a.png"' in out
        assert 'alt="logo"' in out

    def test_text_only_passthrough(self):
        assert sanitize_html("just plain text") == "just plain text"


# ---------------------------------------------------------------------------
# sanitize_html — disallowed tags
# ---------------------------------------------------------------------------


class TestDangerousTags:
    def test_script_tag_removed_with_contents(self):
        out = sanitize_html("<p>safe</p><script>alert(1)</script>")
        assert "<script" not in out
        assert "alert(1)" not in out  # contents removed too
        assert "<p>safe</p>" in out

    def test_style_tag_removed_with_contents(self):
        out = sanitize_html("<style>body{display:none}</style><p>ok</p>")
        assert "<style" not in out
        assert "display:none" not in out
        assert "<p>ok</p>" in out

    def test_iframe_removed(self):
        out = sanitize_html('<iframe src="https://evil"></iframe><p>ok</p>')
        assert "iframe" not in out
        assert "<p>ok</p>" in out

    def test_object_removed(self):
        out = sanitize_html('<object data="x.swf"></object><p>ok</p>')
        assert "object" not in out
        assert "<p>ok</p>" in out

    def test_embed_removed(self):
        out = sanitize_html('<embed src="x.swf"><p>ok</p>')
        assert "embed" not in out
        assert "<p>ok</p>" in out

    def test_form_removed(self):
        out = sanitize_html('<form><input name="a"></form><p>ok</p>')
        assert "<form" not in out
        assert "<input" not in out
        assert "<p>ok</p>" in out

    def test_link_meta_removed(self):
        out = sanitize_html('<link rel="stylesheet" href="x"><meta name="x"><p>ok</p>')
        assert "<link" not in out
        assert "<meta" not in out
        assert "<p>ok</p>" in out


class TestEventHandlerStripping:
    def test_onclick_stripped(self):
        out = sanitize_html('<a href="https://x.com" onclick="alert(1)">x</a>')
        assert "onclick" not in out
        assert 'href="https://x.com"' in out

    def test_onerror_on_image_stripped(self):
        out = sanitize_html('<img src="x.png" onerror="steal()">')
        assert "onerror" not in out

    def test_onload_stripped(self):
        out = sanitize_html('<p onload="x()">hi</p>')
        assert "onload" not in out
        assert "<p>hi</p>" in out

    def test_class_attribute_stripped(self):
        # We deliberately do not allow class to keep the surface area minimal.
        out = sanitize_html('<p class="evil">x</p>')
        assert 'class=' not in out

    def test_style_attribute_stripped(self):
        out = sanitize_html('<p style="color:red">x</p>')
        assert "style=" not in out


class TestProtocolFiltering:
    def test_javascript_link_blocked(self):
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out
        assert "alert(1)" not in out

    def test_data_url_blocked(self):
        out = sanitize_html('<a href="data:text/html,<script>x</script>">x</a>')
        assert "data:" not in out

    def test_http_link_allowed(self):
        out = sanitize_html('<a href="http://example.com">x</a>')
        assert 'href="http://example.com"' in out

    def test_https_link_allowed(self):
        out = sanitize_html('<a href="https://example.com">x</a>')
        assert 'href="https://example.com"' in out

    def test_mailto_link_allowed(self):
        out = sanitize_html('<a href="mailto:foo@example.com">x</a>')
        assert "mailto:foo@example.com" in out


class TestEdgeCases:
    def test_empty_string(self):
        assert sanitize_html("") == ""

    def test_none_input(self):
        assert sanitize_html(None) == ""

    def test_html_comment_removed(self):
        out = sanitize_html("<!-- secret --><p>hi</p>")
        assert "<!--" not in out
        assert "secret" not in out

    def test_nested_dangerous_block(self):
        out = sanitize_html("<p>safe</p><script><script>x</script></script>")
        assert "<script" not in out

    def test_self_closing_iframe(self):
        out = sanitize_html('<iframe src="x"/><p>ok</p>')
        assert "iframe" not in out
        assert "<p>ok</p>" in out

    def test_uppercase_script_tag_removed(self):
        out = sanitize_html("<P>safe</P><SCRIPT>x</SCRIPT>")
        assert "SCRIPT" not in out.upper().replace("DESCRIPT", "")


# ---------------------------------------------------------------------------
# sanitize_sections
# ---------------------------------------------------------------------------


class TestSanitizeSections:
    def test_empty_input(self):
        assert sanitize_sections([]) == []
        assert sanitize_sections(None) == []

    def test_single_section_passes_through_safe_html(self):
        result = sanitize_sections([{"label": "Notes", "html": "<p>hello</p>"}])
        assert result == [{"label": "Notes", "html": "<p>hello</p>"}]

    def test_section_with_dangerous_html_sanitized(self):
        result = sanitize_sections([
            {"label": "Notes", "html": "<p>safe</p><script>alert(1)</script>"},
        ])
        assert "<script" not in result[0]["html"]
        assert "alert(1)" not in result[0]["html"]

    def test_empty_sections_dropped(self):
        result = sanitize_sections([
            {"label": "", "html": ""},
            {"label": "  ", "html": "<p></p>"},
            {"label": "Notes", "html": "<p>real</p>"},
        ])
        assert len(result) == 1
        assert result[0]["label"] == "Notes"

    def test_label_only_section_kept(self):
        """A section with a label but no body is still kept."""
        result = sanitize_sections([{"label": "Empty Section", "html": ""}])
        assert len(result) == 1
        assert result[0]["label"] == "Empty Section"
        assert result[0]["html"] == ""

    def test_html_only_section_kept(self):
        """A section with body but no label is still kept (label becomes blank)."""
        result = sanitize_sections([{"label": "", "html": "<p>orphan</p>"}])
        assert len(result) == 1
        assert result[0]["label"] == ""
        assert "<p>orphan</p>" in result[0]["html"]

    def test_label_stripped_and_capped(self):
        long_label = " " + "A" * 200 + " "
        result = sanitize_sections([{"label": long_label, "html": "<p>x</p>"}])
        assert len(result[0]["label"]) == 128
        assert not result[0]["label"].startswith(" ")

    def test_non_dict_entries_skipped(self):
        result = sanitize_sections([
            "not a dict",
            None,
            {"label": "Notes", "html": "<p>x</p>"},
        ])
        assert len(result) == 1
        assert result[0]["label"] == "Notes"

    def test_multiple_sections_preserved_in_order(self):
        result = sanitize_sections([
            {"label": "First", "html": "<p>a</p>"},
            {"label": "Second", "html": "<p>b</p>"},
            {"label": "Third", "html": "<p>c</p>"},
        ])
        assert [s["label"] for s in result] == ["First", "Second", "Third"]


# ---------------------------------------------------------------------------
# Integration: autosave route sanitises sections end-to-end
# ---------------------------------------------------------------------------


def test_autosave_sanitises_sections_end_to_end(client):
    """The /autosave endpoint must sanitise section HTML before persisting."""
    from app.models import Character, User
    sess = client._test_session_factory()
    sess.add(User(discord_id="183026066498125825", discord_name="Eli", display_name="Eli"))
    c = Character(name="Sanitiser Subject", owner_discord_id="183026066498125825")
    sess.add(c)
    sess.commit()
    char_id = c.id
    sess.close()

    # Send a section that contains BOTH safe and dangerous content
    payload = {
        "sections": [{
            "label": "Notes",
            "html": '<p>safe</p><script>alert(1)</script><a href="javascript:bad()">x</a>',
        }],
    }
    resp = client.post(f"/characters/{char_id}/autosave", json=payload)
    assert resp.status_code == 200

    # Verify the persisted sections are sanitised
    sess = client._test_session_factory()
    refreshed = sess.query(Character).filter(Character.id == char_id).first()
    sect = refreshed.sections
    sess.close()
    assert len(sect) == 1
    assert sect[0]["label"] == "Notes"
    assert "<p>safe</p>" in sect[0]["html"]
    assert "<script" not in sect[0]["html"]
    assert "alert(1)" not in sect[0]["html"]
    assert "javascript:" not in sect[0]["html"]


def test_autosave_drops_empty_sections(client):
    from app.models import Character, User
    sess = client._test_session_factory()
    sess.add(User(discord_id="183026066498125825", discord_name="Eli", display_name="Eli"))
    c = Character(name="Empty Subject", owner_discord_id="183026066498125825")
    sess.add(c)
    sess.commit()
    char_id = c.id
    sess.close()

    payload = {
        "sections": [
            {"label": "", "html": ""},
            {"label": "  ", "html": "<p></p>"},
            {"label": "Real", "html": "<p>kept</p>"},
        ],
    }
    resp = client.post(f"/characters/{char_id}/autosave", json=payload)
    assert resp.status_code == 200

    sess = client._test_session_factory()
    refreshed = sess.query(Character).filter(Character.id == char_id).first()
    assert len(refreshed.sections) == 1
    assert refreshed.sections[0]["label"] == "Real"
    sess.close()
