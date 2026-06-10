use aws_nitro_enclaves_nsm_api::api::{Request, Response};
use aws_nitro_enclaves_nsm_api::driver::{nsm_exit, nsm_init, nsm_process_request};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde_bytes::ByteBuf;
use std::env;
use std::process;

fn decode_optional_b64(arg: Option<&String>) -> Option<ByteBuf> {
    match arg {
        Some(value) if !value.is_empty() => Some(ByteBuf::from(STANDARD.decode(value).unwrap_or_else(|err| {
            eprintln!("base64 decode failed: {err}");
            process::exit(2);
        }))),
        _ => None,
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let user_data = decode_optional_b64(args.get(1));
    let nonce = decode_optional_b64(args.get(2));
    let public_key = decode_optional_b64(args.get(3));

    let fd = nsm_init();
    if fd < 0 {
        eprintln!("failed to open /dev/nsm");
        process::exit(1);
    }

    let request = Request::Attestation {
        user_data,
        nonce,
        public_key,
    };

    let response = nsm_process_request(fd, request);
    nsm_exit(fd);

    match response {
        Response::Attestation { document } => {
            println!("{}", STANDARD.encode(document));
        }
        Response::Error(err) => {
            eprintln!("NSM attestation failed: {err:?}");
            process::exit(1);
        }
        _ => {
            eprintln!("NSM returned an unexpected response");
            process::exit(1);
        }
    }
}
