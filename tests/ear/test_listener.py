# -*- coding: utf-8 -*-
"""Tests de listener.py (Ear, nodos de audio, calibración, detección, grabación, transcripción)."""

from unittest.mock import MagicMock, patch, call

import pytest

from src.ear.listener import (
    AudioCapabilities,
    AudioNode,
    CalibrationNode,
    DetectionNode,
    RecordingNode,
    TranscriptionNode,
    Ear,
)


class TestAudioCapabilities:
    def test_defaults(self):
        caps = AudioCapabilities()
        assert caps.sample_rate == 16000
        assert caps.channels == 1
        assert caps.dtype == "float32"
        assert caps.block_duration == 0.03
        assert caps.max_recording_time == 10.0
        assert caps.silence_threshold == 0.8
        assert caps.sensitivity_multiplier == 3.0

    def test_custom_values(self):
        caps = AudioCapabilities(
            sample_rate=44100, channels=2, dtype="int16",
            block_duration=0.1, max_recording_time=30.0,
            silence_threshold=1.0, sensitivity_multiplier=5.0,
        )
        assert caps.sample_rate == 44100
        assert caps.channels == 2
        assert caps.dtype == "int16"
        assert caps.block_duration == 0.1
        assert caps.max_recording_time == 30.0
        assert caps.silence_threshold == 1.0
        assert caps.sensitivity_multiplier == 5.0


class TestAudioNode:
    def test_init(self):
        node = AudioNode("test_node")
        assert node.name == "test_node"
        assert node.capabilities is not None
        assert isinstance(node.capabilities, AudioCapabilities)

    def test_execute(self):
        node = AudioNode("test_node")
        import numpy as np
        audio = np.array([1.0, 2.0, 3.0])
        result = node.execute(audio)
        assert result["node"] == "test_node"
        assert result["success"] is True
        assert "data" in result

    def test_get_preconditions(self):
        node = AudioNode("test")
        assert node.get_preconditions() == ["audio_available"]

    def test_get_effects(self):
        node = AudioNode("test")
        assert node.get_effects() == ["audio_processed"]

    def test_get_cost(self):
        node = AudioNode("test")
        assert node.get_cost() == 1.0


class TestCalibrationNode:
    def test_init(self):
        node = CalibrationNode("calib")
        assert node.name == "calib"

    def test_execute_with_audio(self):
        import numpy as np
        node = CalibrationNode("calib")
        audio_queue = MagicMock()
        chunks = [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
        audio_queue.empty = MagicMock(side_effect=[False, False, True])
        audio_queue.get = MagicMock(side_effect=chunks)

        result = node.execute(audio_queue)
        assert result["success"] is True
        assert "threshold" in result
        assert "noise_level" in result

    def test_execute_empty_queue(self):
        node = CalibrationNode("calib")
        audio_queue = MagicMock()
        audio_queue.empty = MagicMock(return_value=True)
        result = node.execute(audio_queue)
        assert result["success"] is True
        assert "threshold" in result

    def test_rms_empty(self):
        import numpy as np
        node = CalibrationNode("calib")
        assert node._rms(np.array([])) == 0.0

    def test_rms_non_empty(self):
        import numpy as np
        node = CalibrationNode("calib")
        audio = np.array([3.0, 4.0])
        result = node._rms(audio)
        assert result == 3.5355339059327378  # sqrt((9+16)/2) = sqrt(12.5)


class TestDetectionNode:
    def test_init(self):
        node = DetectionNode("detection")
        assert node.name == "detection"

    @patch("src.ear.listener.time")
    def test_execute_detects_speech(self, mock_time):
        import numpy as np
        mock_time.time = MagicMock(return_value=0.0)
        mock_time.sleep = MagicMock()

        node = DetectionNode("detection")
        audio_queue = MagicMock()
        chunk = np.array([10.0, 20.0])
        audio_queue.empty = MagicMock(side_effect=[False, True])
        audio_queue.get = MagicMock(return_value=MagicMock(flatten=MagicMock(return_value=chunk)))

        result = node.execute(audio_queue, threshold=1.0)
        assert result["success"] is True
        assert result["speech_detected"] is True

    @patch("src.ear.listener.time")
    def test_execute_timeout(self, mock_time):
        mock_time.time = MagicMock(side_effect=[0, 31])  # > 30s timeout
        mock_time.sleep = MagicMock()

        node = DetectionNode("detection")
        audio_queue = MagicMock()
        audio_queue.empty = MagicMock(return_value=True)

        result = node.execute(audio_queue, threshold=1.0)
        assert result["success"] is False
        assert result["speech_detected"] is False


class TestRecordingNode:
    def test_init(self):
        node = RecordingNode("recording")
        assert node.name == "recording"

    @patch("src.ear.listener.time")
    def test_execute_records_audio(self, mock_time):
        import numpy as np
        mock_time.time = MagicMock(return_value=0.0)
        mock_time.sleep = MagicMock()

        node = RecordingNode("recording")
        audio_queue = MagicMock()
        chunk = np.array([1.0, 2.0, 3.0])
        # First iteration: audio > threshold, then silence threshold reached
        audio_queue.empty = MagicMock(side_effect=[False, False, True])
        audio_queue.get = MagicMock(side_effect=[
            MagicMock(flatten=MagicMock(return_value=chunk)),
            MagicMock(flatten=MagicMock(return_value=chunk)),
        ])
        node.capabilities.silence_threshold = 0.5
        # Override RMS to be above threshold first time, below second
        original_rms = node._rms

        calls = [False]
        def mock_rms(audio):
            if not calls[0]:
                calls[0] = True
                return 5.0  # above threshold
            return 0.0  # below threshold → silence accumulates
        node._rms = mock_rms

        result = node.execute(audio_queue, threshold=1.0)
        assert result["success"] is True
        assert "audio" in result
        assert "duration" in result
        assert "chunks_count" in result
        assert result["chunks_count"] >= 1


class TestTranscriptionNode:
    def test_init(self):
        node = TranscriptionNode("transcription")
        assert node.name == "transcription"
        assert node.model_size == "medium"
        assert node.language == "es"
        assert node.model is None

    def test_execute_test_mode(self):
        node = TranscriptionNode("transcription")
        # model is None → returns fixed "hola jarvis"
        import numpy as np
        result = node.execute(np.array([0.1, 0.2]))
        assert result["success"] is True
        assert result["text"] == "hola jarvis"
        assert result["confidence"] == 0.8

    def test_load_model_fallback(self):
        with patch("src.ear.listener.WhisperModel", side_effect=RuntimeError("fail")):
            node = TranscriptionNode("transcription")
            node._load_model()
            assert node.model is None


class TestEar:
    def test_init(self):
        ear = Ear()
        assert ear.model_size == "medium"
        assert ear.language == "es"
        assert ear.calibration_node is not None
        assert ear.detection_node is not None
        assert ear.recording_node is not None
        assert ear.transcription_node is not None
        assert ear.conversation_memory is not None

    def test_init_custom_params(self):
        ear = Ear(model_size="small", language="en")
        assert ear.model_size == "small"
        assert ear.language == "en"

    def test_get_audio_pipeline(self):
        ear = Ear()
        pipeline = ear.get_audio_pipeline()
        assert len(pipeline) == 4
        assert ear.calibration_node in pipeline
        assert ear.detection_node in pipeline
        assert ear.recording_node in pipeline
        assert ear.transcription_node in pipeline

    def test_get_pipeline_cost(self):
        ear = Ear()
        cost = ear.get_pipeline_cost()
        assert cost >= 0.0

    def test_get_pipeline_preconditions(self):
        ear = Ear()
        pre = ear.get_pipeline_preconditions()
        assert "audio_available" in pre

    def test_get_pipeline_effects(self):
        ear = Ear()
        effects = ear.get_pipeline_effects()
        assert "audio_processed" in effects

    def test_check_activation_word_jarvis(self):
        ear = Ear()
        assert ear._check_activation_word("hola jarvis") is True

    def test_check_activation_word_variant(self):
        ear = Ear()
        assert ear._check_activation_word("jarves abre chrome") is True
        assert ear._check_activation_word("garbez") is True

    def test_check_activation_word_none(self):
        ear = Ear()
        assert ear._check_activation_word("hola amigo") is False

    def test_check_activation_word_empty(self):
        ear = Ear()
        assert ear._check_activation_word("") is False

    def test_get_audio_status(self):
        ear = Ear()
        status = ear.get_audio_status()
        assert "model_size" in status
        assert "language" in status
        assert "pipeline_cost" in status
        assert "pipeline_preconditions" in status
        assert "pipeline_effects" in status
        assert "nodes" in status
        assert len(status["nodes"]) == 4

    def test_listen_returns_none_on_exception(self):
        ear = Ear()
        with patch("src.ear.listener.sd.InputStream", side_effect=RuntimeError("fail")):
            result = ear.listen()
            assert result is None

    @patch("src.ear.listener.sd.InputStream")
    def test_listen_success(self, mock_input_stream):
        mock_ctx = MagicMock()
        mock_input_stream.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_input_stream.return_value.__exit__ = MagicMock(return_value=False)

        ear = Ear()
        ear.calibration_node = MagicMock()
        ear.calibration_node.capabilities.sample_rate = 16000
        ear.calibration_node.capabilities.channels = 1
        ear.calibration_node.capabilities.dtype = "float32"
        ear.calibration_node.capabilities.block_duration = 0.03
        ear.calibration_node.execute = MagicMock(return_value={"success": True, "threshold": 1.0})
        ear.detection_node.execute = MagicMock(return_value={"success": True, "speech_detected": True, "chunk": MagicMock()})
        ear.recording_node.execute = MagicMock(return_value={"success": True, "audio": MagicMock()})
        ear.transcription_node.execute = MagicMock(return_value={"success": True, "text": "hola jarvis"})

        with patch.object(ear, "conversation_memory"):
            result = ear.listen()
        assert result == "hola jarvis"

    def test_process_audio_batch_success(self):
        ear = Ear()
        import numpy as np
        chunk = np.array([0.1, 0.2])
        with patch.object(ear.transcription_node, "execute", return_value={"success": True, "text": "hello"}):
            result = ear.process_audio_batch([chunk])
            assert result == "hello"

    def test_process_audio_batch_failure(self):
        ear = Ear()
        import numpy as np
        chunk = np.array([0.1, 0.2])
        with patch.object(ear.transcription_node, "execute", return_value={"success": False, "error": "fail"}):
            result = ear.process_audio_batch([chunk])
            assert result is None

    def test_process_audio_batch_exception(self):
        ear = Ear()
        with patch.object(ear.transcription_node, "execute", side_effect=RuntimeError("fail")):
            result = ear.process_audio_batch([1, 2, 3])
            assert result is None
