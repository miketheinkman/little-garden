// Offers and answers include the browser's gathered host candidates. No external ICE service.
function gardenPeerId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
}

class GardenPeer {
  constructor(id) {
    this.id = id;
    this.pc = new RTCPeerConnection({iceServers: []});
    this.channel = null;
    this.sdp = "";
    this.started = performance.now();
  }

  async gather(description) {
    const pc = this.pc;
    await pc.setLocalDescription(description);
    if (pc.iceGatheringState !== "complete") {
      await new Promise(resolve => {
        const finish = () => {
          clearTimeout(timer);
          pc.removeEventListener("icegatheringstatechange", check);
          resolve();
        };
        const check = () => { if (pc.iceGatheringState === "complete") finish(); };
        const timer = setTimeout(finish, 2000);
        pc.addEventListener("icegatheringstatechange", check);
        check();
      });
    }
    this.sdp = pc.localDescription?.sdp || "";
  }

  async offer(receive) {
    this.channel = this.pc.createDataChannel("garden");
    this.channel.onmessage = event => {
      if (typeof event.data !== "string" || event.data.length > 2048) return;
      try { receive(JSON.parse(event.data)); } catch { /* Ignore an invalid update. */ }
    };
    await this.gather(await this.pc.createOffer());
  }

  async answer(offer) {
    this.pc.ondatachannel = event => {
      if (event.channel.label === "garden" && !this.channel) this.channel = event.channel;
      else event.channel.close();
    };
    await this.pc.setRemoteDescription({type: "offer", sdp: offer});
    await this.gather(await this.pc.createAnswer());
  }

  close() {
    this.channel?.close();
    this.pc.close();
  }
}
