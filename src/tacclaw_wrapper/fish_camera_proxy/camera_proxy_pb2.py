# -*- coding: utf-8 -*-
# Generated from the vendor camera_proxy.proto. DO NOT EDIT.
# ruff: noqa: E501, F401
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database

_sym_db = _symbol_database.Default()

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x12\x63\x61mera_proxy.proto\x12\x15\x66ish_camera.grpc_test\"#\n\x11\x43\x61pabilityRequest\x12\x0e\n\x06\x64\x65vice\x18\x01 \x01(\t\"N\n\x12\x43\x61pabilityResponse\x12\x38\n\x07\x63\x61meras\x18\x01 \x03(\x0b\x32\'.fish_camera.grpc_test.CameraCapability\"Z\n\x10\x43\x61meraCapability\x12\x0e\n\x06\x64\x65vice\x18\x01 \x01(\t\x12\x36\n\x06\x63odecs\x18\x02 \x03(\x0b\x32&.fish_camera.grpc_test.CodecCapability\"L\n\x0f\x43odecCapability\x12\r\n\x05\x63odec\x18\x01 \x01(\t\x12*\n\x05modes\x18\x02 \x03(\x0b\x32\x1b.fish_camera.grpc_test.Mode\"2\n\x04Mode\x12\r\n\x05width\x18\x01 \x01(\x05\x12\x0e\n\x06height\x18\x02 \x01(\x05\x12\x0b\n\x03\x66ps\x18\x03 \x03(\x05\"$\n\x12\x43\x61librationRequest\x12\x0e\n\x06\x64\x65vice\x18\x01 \x01(\t\"\xe7\x01\n\x12IntrinsicsResponse\x12\x0e\n\x06\x64\x65vice\x18\x01 \x01(\t\x12\x14\n\x0c\x63\x61mera_model\x18\x02 \x01(\t\x12\x18\n\x10\x64istortion_model\x18\x03 \x01(\t\x12\x12\n\nintrinsics\x18\x04 \x03(\x01\x12\x15\n\rcamera_matrix\x18\x05 \x03(\x01\x12\x19\n\x11\x64istortion_coeffs\x18\x06 \x03(\x01\x12\x12\n\nresolution\x18\x07 \x03(\x01\x12\n\n\x02sn\x18\x08 \x01(\t\x12\x10\n\x08sn_valid\x18\t \x01(\x08\x12\x19\n\x11\x63\x61mera_model_enum\x18\n \x01(\r\"7\n\nSNResponse\x12\x0e\n\x06\x64\x65vice\x18\x01 \x01(\t\x12\n\n\x02sn\x18\x02 \x01(\t\x12\r\n\x05valid\x18\x03 \x01(\x08\"\x95\x01\n\rStreamRequest\x12\r\n\x05\x63odec\x18\x01 \x01(\t\x12\r\n\x05width\x18\x02 \x01(\x05\x12\x0e\n\x06height\x18\x03 \x01(\x05\x12\x0b\n\x03\x66ps\x18\x04 \x01(\x05\x12\x10\n\x08udp_port\x18\x05 \x01(\x05\x12\x11\n\tclient_ip\x18\x06 \x01(\t\x12\x0e\n\x06\x64\x65vice\x18\x07 \x01(\t\x12\x14\n\x0cmax_datagram\x18\x08 \x01(\x05\"\xc0\x02\n\x0bStreamEvent\x12\x35\n\x04type\x18\x01 \x01(\x0e\x32\'.fish_camera.grpc_test.StreamEvent.Type\x12\x12\n\nsession_id\x18\x02 \x01(\t\x12\x0f\n\x07message\x18\x03 \x01(\t\x12\r\n\x05\x63odec\x18\x04 \x01(\t\x12\r\n\x05width\x18\x05 \x01(\x05\x12\x0e\n\x06height\x18\x06 \x01(\x05\x12\x0b\n\x03\x66ps\x18\x07 \x01(\x05\x12\x0e\n\x06\x64\x65vice\x18\x08 \x01(\t\x12\x13\n\x0b\x66rames_sent\x18\t \x01(\x04\x12\x12\n\nbytes_sent\x18\n \x01(\x04\x12\x13\n\x0b\x65lapsed_sec\x18\x0b \x01(\x01\"L\n\x04Type\x12\x14\n\x10TYPE_UNSPECIFIED\x10\x00\x12\x0b\n\x07STARTED\x10\x01\x12\t\n\x05STATS\x10\x02\x12\x0b\n\x07STOPPED\x10\x03\x12\t\n\x05\x45RROR\x10\x04\"\'\n\x11StopStreamRequest\x12\x12\n\nsession_id\x18\x01 \x01(\t\"6\n\x12StopStreamResponse\x12\x0f\n\x07stopped\x18\x01 \x01(\x08\x12\x0f\n\x07message\x18\x02 \x01(\t2\xf1\x03\n\x0b\x43\x61meraProxy\x12g\n\x10ListCapabilities\x12(.fish_camera.grpc_test.CapabilityRequest\x1a).fish_camera.grpc_test.CapabilityResponse\x12\x65\n\rGetIntrinsics\x12).fish_camera.grpc_test.CalibrationRequest\x1a).fish_camera.grpc_test.IntrinsicsResponse\x12U\n\x05GetSN\x12).fish_camera.grpc_test.CalibrationRequest\x1a!.fish_camera.grpc_test.SNResponse\x12X\n\nOpenStream\x12$.fish_camera.grpc_test.StreamRequest\x1a\".fish_camera.grpc_test.StreamEvent0\x01\x12\x61\n\nStopStream\x12(.fish_camera.grpc_test.StopStreamRequest\x1a).fish_camera.grpc_test.StopStreamResponseb\x06proto3')

def _message_class(name):
    message_class = _reflection.GeneratedProtocolMessageType(
        name,
        (_message.Message,),
        {
            "DESCRIPTOR": DESCRIPTOR.message_types_by_name[name],
            "__module__": __name__,
        },
    )
    _sym_db.RegisterMessage(message_class)
    return message_class


CapabilityRequest = _message_class("CapabilityRequest")
CapabilityResponse = _message_class("CapabilityResponse")
CameraCapability = _message_class("CameraCapability")
CodecCapability = _message_class("CodecCapability")
Mode = _message_class("Mode")
CalibrationRequest = _message_class("CalibrationRequest")
IntrinsicsResponse = _message_class("IntrinsicsResponse")
SNResponse = _message_class("SNResponse")
StreamRequest = _message_class("StreamRequest")
StreamEvent = _message_class("StreamEvent")
StopStreamRequest = _message_class("StopStreamRequest")
StopStreamResponse = _message_class("StopStreamResponse")
