"""Tests for filtergraph builder."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.renderer.filtergraph import FilterNode, FilterGraph, FilterGraphError


class TestFilterNode:
    def test_basic_render(self):
        node = FilterNode(
            name="scale",
            inputs=["[0:v]"],
            outputs=["[scaled]"],
            params={"w": "1080", "h": "1080"},
        )
        result = node.to_str()
        assert result == "[0:v]scale=w=1080:h=1080[scaled]"

    def test_no_params(self):
        node = FilterNode("split", ["[0:v]"], ["[a]", "[b]"], {})
        result = node.to_str()
        assert result == "[0:v]split[a][b]"

    def test_multiple_inputs(self):
        node = FilterNode("overlay", ["[bg]", "[fg]"], ["[out]"], {"x": "0", "y": "0"})
        result = node.to_str()
        assert result == "[bg][fg]overlay=x=0:y=0[out]"

    def test_param_order_preserved(self):
        node = FilterNode("drawbox", ["[v]"], ["[out]"], {
            "x": "0", "y": "700", "w": "1080", "h": "80",
            "color": "0xFF0000FF", "t": "fill"
        })
        result = node.to_str()
        # All params should appear in insertion order
        assert result.index("x=0") < result.index("y=700")
        assert result.index("w=1080") < result.index("color=")


class TestFilterGraph:
    def test_build_single_node(self):
        fg = FilterGraph()
        fg.add(FilterNode("scale", ["[0:v]"], ["[out]"], {"w": "1080"}))
        fg.set_final_output("[out]")
        result = fg.build()
        assert "[final]" in result
        assert "[out]" not in result  # replaced by [final]

    def test_build_multi_node(self):
        fg = FilterGraph()
        fg.add(FilterNode("scale", ["[0:v]"], ["[scaled]"], {"w": "1080", "h": "1080"}))
        fg.add(FilterNode("drawbox", ["[scaled]"], ["[boxed]"], {
            "x": "0", "y": "0", "w": "1080", "h": "1080",
            "color": "0x00000072", "t": "fill"
        }))
        fg.set_final_output("[boxed]")
        result = fg.build()
        assert "; " in result  # nodes separated by semicolons
        assert "[final]" in result

    def test_raises_without_final_output(self):
        fg = FilterGraph()
        fg.add(FilterNode("scale", ["[0:v]"], ["[s]"], {"w": "1080"}))
        with pytest.raises(FilterGraphError, match="final_output"):
            fg.build()

    def test_chaining_returns_self(self):
        fg = FilterGraph()
        result = fg.add(FilterNode("scale", ["[0:v]"], ["[s]"], {}))
        assert result is fg

    def test_empty_graph_raises(self):
        fg = FilterGraph()
        fg.set_final_output("[final]")
        # No nodes added — build should still work but produce empty string
        # (FFmpeg will error, but FilterGraph itself shouldn't crash)
        result = fg.build()
        assert isinstance(result, str)


class TestColorUtils:
    def test_hex_to_ffmpeg_text(self):
        from src.utils.color import hex_to_ffmpeg_text
        assert hex_to_ffmpeg_text("#1B2A4A") == "0x1B2A4A"
        assert hex_to_ffmpeg_text("C8102E") == "0xC8102E"

    def test_hex_to_ffmpeg_box_opaque(self):
        from src.utils.color import hex_to_ffmpeg_box
        result = hex_to_ffmpeg_box("#C8102E", 1.0)
        assert result == "0xC8102EFF"

    def test_hex_to_ffmpeg_box_transparent(self):
        from src.utils.color import hex_to_ffmpeg_box
        result = hex_to_ffmpeg_box("#000000", 0.0)
        assert result == "0x00000000"

    def test_hex_to_ffmpeg_box_half_alpha(self):
        from src.utils.color import hex_to_ffmpeg_box
        result = hex_to_ffmpeg_box("#FFFFFF", 0.5)
        # 0.5 * 255 = 127 = 0x7F
        assert result == "0xFFFFFF7F"

    def test_invalid_hex_raises(self):
        from src.utils.color import hex_to_ffmpeg_text
        with pytest.raises(ValueError):
            hex_to_ffmpeg_text("#GGGGGG")

    def test_alpha_out_of_range_raises(self):
        from src.utils.color import hex_to_ffmpeg_box
        with pytest.raises(ValueError):
            hex_to_ffmpeg_box("#FFFFFF", 1.5)
