# Commercial License for HF Downloader

HF Downloader is open source under the [GNU Affero General Public License v3.0 or later](https://www.gnu.org/licenses/agpl-3.0.html) (AGPLv3). The AGPLv3 requires that anyone who runs a modified version of the software as a network service, or who distributes a modified version, must make the complete corresponding source code available under the same terms.

That's good for most people. But not everyone can (or wants to) comply with those terms. If your use case falls into one of the categories below, a **commercial license** removes the AGPLv3 obligations and lets you use the software under terms you negotiate directly with the maintainer.

---

## When you might need a commercial license

A commercial license is appropriate if you want to do **any** of the following without open-sourcing your changes:

- **Embed** HF Downloader (or a modified version) into a **proprietary product** that you sell or distribute.
- **Distribute a modified, closed-source fork** (for example, as part of a paid software bundle, a corporate internal tool, or a partner SDK).
- **Run HF Downloader as a hosted / SaaS service** and keep the modifications proprietary.
- **Bundle HF Downloader with proprietary commercial software** under terms that conflict with AGPLv3.
- **Use HF Downloader in a regulated environment** (financial, medical, defense) where AGPLv3 obligations on downstream parties are a problem.

If you're an **individual user** who just wants to download models from Hugging Face on your own computer — **you don't need a commercial license**. The AGPLv3 is free and grants you that right.

If you're **distributing the original, unmodified** HF Downloader binaries (e.g., including them in a Linux distro or a public mirror) — **you don't need a commercial license either**, as long as you comply with the AGPLv3 (basically: pass the license and source along).

---

## What's typically included

A commercial license is a private agreement between you and the maintainer. Terms are flexible and depend on what you need, but typically include:

- **A non-exclusive, non-transferable** right to use, modify, and distribute HF Downloader (or a derivative) under terms that don't include the AGPLv3 copyleft obligations.
- **Source-available modifications** — you keep your changes private, no obligation to publish them.
- **No requirement to disclose** your customer list, internal architecture, or other proprietary information.
- **A specific scope** — for example, "internal use within Company X's engineering team" or "redistribution as part of Product Y up to N seats".
- **Optional support** — at additional cost, the maintainer can provide a service-level agreement for bug fixes and feature work.

The maintainer will work with you to draft terms that fit your situation. There's no template that's right for everyone.

---

## What is **not** included by default

- **The "HF Downloader" name and logo** are not granted. If you fork and rebrand (which is fine), pick your own name. The original name stays with the maintainer's distribution.
- **Trademark rights** to "Hugging Face" or anything owned by Hugging Face, Inc. (This project is an unofficial community tool.)
- **Warranties** that the software is fit for any particular purpose. (Same as AGPLv3 — software is provided "as is". Warranty can be added as a paid extra.)

---

## How to start a conversation

Open a GitHub issue using the **License inquiry** template at:
- https://github.com/alexveliyar-coder/HF-Downloader/issues/new?template=license.yml

Please share:

1. **What you're building** — short description (1-2 paragraphs). Doesn't have to be secret; a rough idea is enough.
2. **How HF Downloader fits in** — embedded in your product? Run as a service? Distributed to your customers? Internal use only?
3. **Expected scale** — number of end users / installs / monthly active users, if you can share.
4. **Timeline** — when you want to ship.
5. **Budget range** — even a rough number helps narrow the conversation. (If you genuinely have no budget, say so — sometimes a non-commercial arrangement is possible for non-profits, education, personal use, etc.)

You don't need to share source code or proprietary details at this stage. The maintainer will reply with questions and (if there's a fit) a draft agreement.

---

## Things the maintainer will not do

- **Sell exclusive rights** to the codebase. The AGPLv3 grant to the public is permanent. A commercial license can only grant *additional* rights, not take away the public's right to use HF Downloader under AGPLv3.
- **Transfer ownership of the project** without due process. (If you want to buy the project outright, that's a different conversation — see below.)
- **Sign a deal that would force a name change or hostile rebrand** of the existing community distribution. Existing users won't lose their rights.

---

## About selling the whole project

If you're a company or individual interested in **acquiring HF Downloader outright** (transferring copyright and trademarks, sunsetting the public project, etc.), please reach out via the same license inquiry form. That's a separate kind of deal with different economics, and the maintainer will treat it as such.

---

## Why dual licensing at all?

Most users — the vast majority — will use HF Downloader under AGPLv3, for free, and that's great. The dual-license exists so that the project can also work as a sustainable foundation: if a company needs to use it under different terms, they pay for that convenience, and that revenue supports the maintainer continuing to work on the open-source version that everyone else uses.

It's the same model used by:
- MongoDB (SSPL + commercial)
- Sentry (BSL + commercial)
- HashiCorp (BUSL + community editions)
- Bitwarden (AGPLv3 + commercial)

These projects are widely used and well-loved in the open-source community. The commercial license is an *option*, not a *requirement*, and most users never need it.

---

*This document is informational and not a binding offer. Actual commercial license terms are negotiated per-customer.*
