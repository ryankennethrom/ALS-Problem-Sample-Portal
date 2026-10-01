'use client';

import { useEffect, useRef, useState } from 'react';

type CameraCaptureProps = {
  onCapture: (file: File) => void | Promise<void>;
  disabled?: boolean;
  buttonLabel?: string;
};

function photoFilename() {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `ticket-photo-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.jpg`;
}

export default function CameraCapture({ onCapture, disabled = false, buttonLabel = 'Take Photo' }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');

  function stopCamera() {
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  function closeCamera() {
    stopCamera();
    setOpen(false);
    setError('');
  }

  useEffect(() => {
    return () => stopCamera();
  }, []);

  async function startCamera() {
    if (disabled) return;
    setOpen(true);
    setStarting(true);
    setError('');
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is not supported by this browser.');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch (cameraError) {
      stopCamera();
      const message = cameraError instanceof Error ? cameraError.message : 'Could not access the camera.';
      setError(message || 'Could not access the camera. Check the browser camera permission and try again.');
    } finally {
      setStarting(false);
    }
  }

  async function capturePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight || capturing) return;
    setCapturing(true);
    setError('');
    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Could not capture the camera image.');
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));
      if (!blob) throw new Error('Could not create the captured image.');
      const file = new File([blob], photoFilename(), { type: 'image/jpeg', lastModified: Date.now() });
      await onCapture(file);
      closeCamera();
    } catch (captureError) {
      setError(captureError instanceof Error ? captureError.message : 'Could not capture the photo.');
    } finally {
      setCapturing(false);
    }
  }

  return <>
    <button type="button" className="button secondary camera-button" onClick={startCamera} disabled={disabled}>{buttonLabel}</button>
    {open && <div className="camera-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !capturing) closeCamera(); }}>
      <div className="camera-dialog" role="dialog" aria-modal="true" aria-labelledby="camera-title">
        <div className="camera-header">
          <div>
            <h2 id="camera-title">Take a ticket photo</h2>
            <div className="muted camera-subtitle">Use the camera to capture an image directly. The photo is saved as JPEG.</div>
          </div>
          <button type="button" className="button secondary" onClick={closeCamera} disabled={capturing}>Close</button>
        </div>
        <div className="camera-preview-wrap">
          <video ref={videoRef} className="camera-preview" autoPlay playsInline muted />
          {starting && <div className="camera-preview-message">Starting camera…</div>}
          {!starting && error && <div className="camera-preview-message camera-preview-error">{error}</div>}
        </div>
        <div className="camera-actions">
          <button type="button" className="button secondary" onClick={closeCamera} disabled={capturing}>Cancel</button>
          <button type="button" className="button camera-shutter" onClick={capturePhoto} disabled={starting || Boolean(error) || capturing}>{capturing ? 'Saving…' : 'Take Photo'}</button>
        </div>
        <div className="muted camera-permission-note">Camera access requires browser permission and works on HTTPS or localhost.</div>
      </div>
    </div>}
  </>;
}
