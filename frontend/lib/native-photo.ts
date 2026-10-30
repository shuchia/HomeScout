// Photo capture in the mobile apps. The WebView's own <input type="file">
// picker silently does nothing in the iOS app, so there the native camera
// plugin is used instead: one sheet offering "Take Photo" or the library.
// Imported lazily — the website never loads it.

/** Ask the user for a photo. Resolves to null if they cancel. */
export async function pickNativePhoto(): Promise<File | null> {
  const { Camera, CameraResultType, CameraSource } = await import('@capacitor/camera')
  let photo
  try {
    photo = await Camera.getPhoto({
      source: CameraSource.Prompt,
      // Base64, not a file URI: the page is served from snugd.ai, which
      // can't fetch the plugin's capacitor:// file URLs.
      resultType: CameraResultType.Base64,
      quality: 85,
      width: 2048, // longest side; keeps uploads well under the 10 MB cap
      correctOrientation: true,
      promptLabelHeader: 'Add a photo',
      promptLabelPhoto: 'Choose from Library',
      promptLabelPicture: 'Take Photo',
    })
  } catch (e) {
    // Cancelling either sheet rejects; that is not an error to show.
    if (/cancel/i.test(String((e as Error)?.message ?? e))) return null
    throw e
  }
  if (!photo.base64String) return null
  const type = `image/${photo.format === 'jpg' ? 'jpeg' : photo.format}`
  const bytes = Uint8Array.from(atob(photo.base64String), c => c.charCodeAt(0))
  return new File([bytes], `photo.${photo.format}`, { type })
}
