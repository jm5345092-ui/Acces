import javax.imageio.ImageIO;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.File;

/**
 * Genera los iconos de la app a partir de una imagen (PNG/JPG).
 * Uso: java IconGen.java <imagen> <carpeta res> <#colorFondo>
 *
 * Crea en cada mipmap-*dpi:
 *   ic_launcher.png / ic_launcher_round.png  (icono clásico, imagen sobre el color de fondo)
 *   ic_launcher_foreground.png               (capa frontal del icono adaptativo, imagen al 66% centrada)
 */
public class IconGen {
    static final String[] DENSITIES = {"mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"};
    static final int[] LEGACY   = {48, 72, 96, 144, 192};
    static final int[] ADAPTIVE = {108, 162, 216, 324, 432};

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("Uso: IconGen <imagen> <res> <#color>");
            System.exit(1);
        }
        BufferedImage src = ImageIO.read(new File(args[0]));
        if (src == null) {
            System.err.println("Formato de imagen no soportado: " + args[0]);
            System.exit(1);
        }
        File res = new File(args[1]);
        Color bg = Color.decode(args[2]);

        BufferedImage square = cropSquare(src);

        for (int i = 0; i < DENSITIES.length; i++) {
            File dir = new File(res, "mipmap-" + DENSITIES[i]);
            dir.mkdirs();

            // Icono clásico: fondo de color + imagen ocupando todo el cuadro
            BufferedImage legacy = new BufferedImage(LEGACY[i], LEGACY[i], BufferedImage.TYPE_INT_ARGB);
            Graphics2D g = hq(legacy.createGraphics());
            g.setColor(bg);
            g.fillRect(0, 0, LEGACY[i], LEGACY[i]);
            g.drawImage(square, 0, 0, LEGACY[i], LEGACY[i], null);
            g.dispose();
            ImageIO.write(legacy, "png", new File(dir, "ic_launcher.png"));
            ImageIO.write(legacy, "png", new File(dir, "ic_launcher_round.png"));

            // Capa frontal adaptativa: transparente, imagen al 66% (zona segura)
            int size = ADAPTIVE[i];
            int inner = Math.round(size * 0.66f);
            int off = (size - inner) / 2;
            BufferedImage fg = new BufferedImage(size, size, BufferedImage.TYPE_INT_ARGB);
            g = hq(fg.createGraphics());
            g.drawImage(square, off, off, inner, inner, null);
            g.dispose();
            ImageIO.write(fg, "png", new File(dir, "ic_launcher_foreground.png"));
        }
        System.out.println("Iconos generados en " + res.getPath());
    }

    static Graphics2D hq(Graphics2D g) {
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        return g;
    }

    /** Recorta la imagen al cuadrado central y la convierte a ARGB. */
    static BufferedImage cropSquare(BufferedImage src) {
        int s = Math.min(src.getWidth(), src.getHeight());
        int x = (src.getWidth() - s) / 2;
        int y = (src.getHeight() - s) / 2;
        BufferedImage out = new BufferedImage(s, s, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = out.createGraphics();
        g.drawImage(src.getSubimage(x, y, s, s), 0, 0, null);
        g.dispose();
        return out;
    }
}
