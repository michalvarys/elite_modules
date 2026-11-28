import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

const HEX_COLOR = /^#[0-9a-f]{6}$/i;
const DARK_TEXT = "#212529";

function luminance(hex) {
    const [r, g, b] = [1, 3, 5].map((i) => {
        const c = parseInt(hex.slice(i, i + 2), 16) / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** White or dark text, whichever contrasts more with the background (WCAG contrast ratio). */
export function readableTextColor(background) {
    const bg = luminance(background);
    const white = 1.05 / (bg + 0.05);
    const dark = (Math.max(bg, luminance(DARK_TEXT)) + 0.05) / (Math.min(bg, luminance(DARK_TEXT)) + 0.05);
    return white >= dark ? "#FFFFFF" : DARK_TEXT;
}

/** Inline Bootstrap button variables for a payment method with a colour, "" without one. */
export function paymentButtonStyle(color) {
    if (!color || !HEX_COLOR.test(color)) {
        return "";
    }
    const text = readableTextColor(color);
    return ["", "-hover", "-active", "-disabled"]
        .map((state) => `--btn${state}-bg: ${color}; --btn${state}-border-color: ${color}; --btn${state}-color: ${text};`)
        .join(" ");
}

patch(PaymentScreen.prototype, {
    paymentMethodButtonStyle(paymentMethod) {
        return paymentButtonStyle(paymentMethod.pos_button_color);
    },
});
